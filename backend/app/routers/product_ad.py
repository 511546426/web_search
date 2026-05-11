"""商品带货视频 API — 步骤化制作流程.

流程：
  上传素材 → [商标合成预览 → 确认] → 生成带货剧本 → [确认剧本] → 生成视频
  每步支持确认/重试，用户可以在进入下一步前预览结果。
"""
import json
import os
import logging
import threading
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from fastapi import Depends

from app.database import get_db
from app.models import ProductAd
from app.schemas import (
    ProductInfoRequest, ProductAdScriptResponse,
    CompositePreviewResponse, CompositePreviewItem,
    CompositeConfirmRequest, ScriptRetryRequest,
)

logger = logging.getLogger("product_ad")

router = APIRouter(prefix="/api/comic/product-ad", tags=["product_ad"])

PRODUCT_PHOTO_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "uploads",
    "product_photos",
)
os.makedirs(PRODUCT_PHOTO_DIR, exist_ok=True)

PUBLIC_URL = os.environ.get("PUBLIC_URL", "").rstrip("/")


def _photo_url(filename: str) -> str:
    if PUBLIC_URL:
        return f"{PUBLIC_URL}/uploads/product_photos/{filename}"
    return f"/uploads/product_photos/{filename}"


# ==============================================================
# 图片/视频上传（保持不变）
# ==============================================================

@router.post("/upload-photos")
def upload_photos(files: List[UploadFile] = File(...)):
    if len(files) > 9:
        raise HTTPException(status_code=400, detail="最多上传 9 张图片")
    saved = []
    for f in files:
        ext = os.path.splitext(f.filename or ".jpg")[1] or ".jpg"
        name = f"prod_{datetime.utcnow():%Y%m%d%H%M%S%f}_{len(saved)}{ext}"
        path = os.path.join(PRODUCT_PHOTO_DIR, name)
        content = f.file.read()
        with open(path, "wb") as out:
            out.write(content)
        saved.append(name)
        logger.info(f"Product photo saved: {name} ({len(content)} bytes)")
    return {"photo_ids": saved, "count": len(saved)}


@router.post("/upload-video")
def upload_product_video(file: UploadFile = File(...)):
    import subprocess
    import tempfile
    suffix = os.path.splitext(file.filename or ".mp4")[1] or ".mp4"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file.file.read())
        tmp_path = tmp.name
    try:
        dur_result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", tmp_path],
            capture_output=True, text=True, timeout=30,
        )
        duration = float(dur_result.stdout.strip())
        if duration <= 0:
            raise HTTPException(status_code=400, detail="无法获取视频时长")
        max_frames = 9
        interval = duration / max_frames
        base = f"vid_{datetime.utcnow():%Y%m%d%H%M%S%f}"
        extracted = []
        for i in range(max_frames):
            seek_time = i * interval
            out_name = f"{base}_{i}.jpg"
            out_path = os.path.join(PRODUCT_PHOTO_DIR, out_name)
            subprocess.run(
                ["ffmpeg", "-ss", str(seek_time), "-i", tmp_path,
                 "-vframes", "1", "-q:v", "2", out_path, "-y"],
                capture_output=True, timeout=60,
            )
            if os.path.getsize(out_path) > 0:
                extracted.append(out_name)
        if not extracted:
            raise HTTPException(status_code=500, detail="视频抽帧失败")
        return {"photo_ids": extracted, "count": len(extracted), "source_video": file.filename}
    finally:
        os.unlink(tmp_path)


# ==============================================================
# 创建草稿（步骤 0：先创建 ad 记录，后续步骤在此基础上进行）
# ==============================================================

@router.post("/create-draft", status_code=201)
def create_draft(body: ProductInfoRequest, db: Session = Depends(get_db)):
    """创建商品带货草稿，返回 ad_id，后续步骤基于此 ad_id 进行。"""
    ad = ProductAd(
        title=body.name or "商品带货视频",
        product_info=json.dumps(body.model_dump(), ensure_ascii=False),
        photo_ids=json.dumps(body.photo_ids, ensure_ascii=False),
        script_content="{}",
        status="draft",
        tags="带货",
    )
    db.add(ad)
    db.commit()
    db.refresh(ad)
    logger.info(f"Draft created: id={ad.id}, title={ad.title}")
    return {"ad_id": ad.id, "message": "草稿已创建"}


# ==============================================================
# 商标合成预览（步骤 1）
# ==============================================================

@router.post("/{ad_id}/preview-composite", response_model=CompositePreviewResponse)
def preview_composite(ad_id: int, db: Session = Depends(get_db)):
    """检测服装照片是否需要合成商标，返回合成预览结果。"""
    from app.services.doubao_vision_client import analyze_product_images
    from app.services.compositor import composite_logo_to_garment

    ad = db.query(ProductAd).filter(ProductAd.id == ad_id).first()
    if not ad:
        raise HTTPException(status_code=404, detail="草稿不存在")

    photo_ids = json.loads(ad.photo_ids) if isinstance(ad.photo_ids, str) else (ad.photo_ids or [])
    if not photo_ids:
        raise HTTPException(status_code=400, detail="请先上传商品照片")

    # 区分服装照片和商标照片（简单启发：至少有一张图名含 logo/label/商标/标 视为商标图）
    logo_photo_id = None
    garment_ids = []
    for pid in photo_ids:
        lower = pid.lower()
        if any(kw in lower for kw in ["logo", "label", "商标", "标", "tag"]):
            logo_photo_id = pid
        else:
            garment_ids.append(pid)

    # 如果没有明显标识的商标图，无法合成
    if not logo_photo_id:
        return CompositePreviewResponse(
            ad_id=ad_id,
            items=[CompositePreviewItem(
                photo_id=pid,
                photo_url=_photo_url(pid),
                garment_type="",
                position=None,
                logo_visible=False,
                confirmed=False,
            ) for pid in garment_ids],
        )

    logo_path = os.path.join(PRODUCT_PHOTO_DIR, logo_photo_id)
    if not os.path.exists(logo_path):
        raise HTTPException(status_code=400, detail="商标照片文件不存在")

    # 尝试用豆包视觉分析服装照片，推断服装类型和推荐落标位置
    garment_paths = [os.path.join(PRODUCT_PHOTO_DIR, pid) for pid in garment_ids if os.path.exists(os.path.join(PRODUCT_PHOTO_DIR, pid))]

    # 默认位置映射
    garment_info = []
    for pid in garment_ids:
        path = os.path.join(PRODUCT_PHOTO_DIR, pid)
        if not os.path.exists(path):
            continue
        garment_info.append({"photo_id": pid, "path": path, "position": "左胸前", "garment_type": ""})

    # 如果有豆包 vision，尝试分析每件服装的类型和推荐位置
    if garment_paths:
        try:
            product_info = json.loads(ad.product_info) if isinstance(ad.product_info, str) else {}
            analysis_text = analyze_product_images(
                image_paths=garment_paths + [logo_path],
                product_name=product_info.get("name", ""),
                product_category=product_info.get("category", ""),
            )
            # 从分析文本中尝试提取服装类型和位置信息
            logger.info(f"Composite preview analysis done, text length: {len(analysis_text)}")
        except Exception as e:
            logger.warning(f"Vision analysis for composite failed: {e}")

    # 执行合成
    items = []
    for gi in garment_info:
        out = composite_logo_to_garment(
            garment_path=gi["path"],
            logo_path=logo_path,
            position=gi["position"],
            output_dir=PRODUCT_PHOTO_DIR,
        )
        photo_id = os.path.basename(out) if out else gi["photo_id"]
        items.append(CompositePreviewItem(
            photo_id=photo_id,
            photo_url=_photo_url(photo_id),
            garment_type=gi["garment_type"],
            position=gi["position"],
            logo_visible=True,
            confirmed=False,
        ))

    return CompositePreviewResponse(ad_id=ad_id, items=items)


@router.post("/{ad_id}/retry-composite", response_model=CompositePreviewResponse)
def retry_composite(
    ad_id: int,
    body: dict = None,
    db: Session = Depends(get_db),
):
    """重新合成商标，可指定新的落标位置。"""
    from app.services.compositor import composite_logo_to_garment

    ad = db.query(ProductAd).filter(ProductAd.id == ad_id).first()
    if not ad:
        raise HTTPException(status_code=404, detail="草稿不存在")

    positions = (body or {}).get("positions", {})
    photo_ids = json.loads(ad.photo_ids) if isinstance(ad.photo_ids, str) else (ad.photo_ids or [])

    # 找商标图
    logo_photo_id = None
    garment_ids = []
    for pid in photo_ids:
        lower = pid.lower()
        if any(kw in lower for kw in ["logo", "label", "商标", "标", "tag"]):
            logo_photo_id = pid
        else:
            garment_ids.append(pid)

    if not logo_photo_id:
        raise HTTPException(status_code=400, detail="未找到商标照片")

    logo_path = os.path.join(PRODUCT_PHOTO_DIR, logo_photo_id)
    ad.composite_retry_count = (ad.composite_retry_count or 0) + 1
    db.commit()

    items = []
    for pid in garment_ids:
        pos = positions.get(pid, "左胸前")
        garment_path = os.path.join(PRODUCT_PHOTO_DIR, pid)
        if not os.path.exists(garment_path):
            continue
        out = composite_logo_to_garment(
            garment_path=garment_path,
            logo_path=logo_path,
            position=pos,
            output_dir=PRODUCT_PHOTO_DIR,
        )
        photo_id = os.path.basename(out) if out else pid
        items.append(CompositePreviewItem(
            photo_id=photo_id,
            photo_url=_photo_url(photo_id),
            garment_type="",
            position=pos,
            logo_visible=True,
            confirmed=False,
        ))

    return CompositePreviewResponse(ad_id=ad_id, items=items)


@router.post("/{ad_id}/confirm-composite")
def confirm_composite(ad_id: int, body: CompositeConfirmRequest, db: Session = Depends(get_db)):
    """确认商标合成结果。"""
    ad = db.query(ProductAd).filter(ProductAd.id == ad_id).first()
    if not ad:
        raise HTTPException(status_code=404, detail="草稿不存在")
    ad.composite_confirmed = True
    ad.composite_photo_ids = json.dumps(body.photo_ids, ensure_ascii=False)
    db.commit()
    logger.info(f"Composite confirmed for ad {ad_id}: {len(body.photo_ids)} photos")
    return {"message": "合成已确认", "ad_id": ad_id}


# ==============================================================
# 生成带货剧本（步骤 2）
# ==============================================================

def _generate_ad_script(product: ProductInfoRequest, user_feedback: str = "") -> dict:
    """生成带货剧本（可接受用户补充要求）。"""
    from app.services.deepseek_client import chat_json
    from app.services.doubao_vision_client import analyze_product_images

    # 使用合成后的照片（如果有）进行视觉分析
    image_paths = []
    for pid in product.photo_ids:
        if not pid:
            continue
        img_path = os.path.join(PRODUCT_PHOTO_DIR, pid)
        if os.path.exists(img_path):
            image_paths.append(img_path)

    image_description = ""
    if image_paths:
        try:
            image_description = analyze_product_images(
                image_paths=image_paths,
                product_name=product.name,
                product_category=product.category,
            )
            logger.info(f"Doubao vision analysis done, desc length: {len(image_description)}")
        except Exception as e:
            logger.exception(f"Doubao vision analysis failed: {e}")
            image_description = f"（图片分析失败: {e}，请根据商品信息生成剧本）"

    visual_style_text = "真人实景拍摄，真人出镜或产品实拍展示" if product.visual_style == "realistic" else "动漫风格，二维动画展示产品"
    style_note = "写实、真实产品展示" if product.visual_style == "realistic" else "二次元动漫风格"

    if product.showcase_style == "visual":
        system = _build_visual_system_prompt(product, style_note)
    else:
        system = _build_story_system_prompt(product, style_note)

    image_section = ""
    if image_description:
        image_section = f"""
===== 商品图片视觉分析（由 AI 视觉模型识别）=====

{image_description}

===== 视觉分析结束 =====
"""

    user_feedback_section = ""
    if user_feedback:
        user_feedback_section = f"""
===== 用户补充要求 =====

{user_feedback}

===== 补充要求结束 =====
"""

    prompt = f"""{image_section}{user_feedback_section}Based on the above visual analysis of {len(image_paths)} product photos, create a short e-commerce video script.

IMPORTANT: The visual analysis above describes EXACTLY what the product looks like in the uploaded photos.
- Product appearance (color, shape, material, details): strictly follow the analysis, do NOT invent features.
- Scene backgrounds: do NOT copy the photo's plain studio background. Use ONE unified real-world location for the whole video.

Product info:
- Name: {product.name}
- Category: {product.category}
- Description: {product.description}
- Selling points: {product.selling_points}
- Target audience: {product.target_audience}
- Style preference: {product.style_preference or 'Not specified'}
- Showcase mode: {'Visual showcase (no dialogue)' if product.showcase_style == 'visual' else 'Story-driven drama'}

CRITICAL RULES:
1. Product features (product_focus) must reference actual features from the visual analysis.
2. ALL scenes in ONE unified real-world location. NEVER use plain/solid color backgrounds.
3. **LOGO REQUIREMENT**: The product has a logo/brand mark on it (visible in reference photos). Every scene's camera angle must show the logo naturally. Include at least ONE dedicated close-up emphasizing the logo detail.
4. Total video duration: ~15 seconds. Return ONLY the JSON."""
    result = chat_json(prompt, system=system, temperature=0.7, max_tokens=4096)
    result["visual_style"] = product.visual_style
    result["showcase_style"] = product.showcase_style
    result["image_description"] = image_description
    return result


def _build_visual_system_prompt(product, style_note):
    return f"""你是一名从业 15 年的时尚广告导演。你擅长用纯视觉语言讲述产品故事。
## 视觉叙事体系
- Establishing → Detail → Motion → Lifestyle → Climax
## 镜头语言
景别：远景全身、中景半身、近景特写、大特写
角度序列：正面 → 侧面 → 背面 → 3/4 → 动态 → 特写
运镜：固定、缓慢推近、环绕、跟随、升降
## 场景背景设计
- 禁止纯色背景/摄影棚/白墙
- 所有场景在同一实景环境中（禁止咖啡馆/红砖墙/水泥墙）
- 根据品类选择匹配场景（服装→街头/海滨/公园/画廊/天台等）
- 同一环境内不同区域变化
## LOGO 要求
- 商品上有品牌商标/图案，必须在每个场景中自然可见
- 至少一个特写镜头聚焦商标细节
输出 JSON 结构：
{{
  "title": "...", "product": "...", "genre": "带货/穿搭展示", "theme": "...",
  "showcase_style": "visual", "visual_style": "{product.visual_style}",
  "setting": "统一场景环境描述",
  "scenes": [{{"scene": 1, "camera_angle": "...", "action": "...", "product_focus": "...", "duration_seconds": 2}}],
  "duration_estimate": 15, "tags": [], "background_music": "..."
}}"""


def _build_story_system_prompt(product, style_note):
    return f"""你是一名头部 MCN 创意总监，擅长制作"看了就想买"的电商短视频。
## 黄金开场
痛点直击 / 结果展示 / 悬念提问 / 冲突引入
## 产品展示体系
场景 1-2：建立需求 → 场景 3-5：产品解决方案 → 场景 6-7：信任建立 → 场景 8：CTA
## 场景背景设计
- 禁止纯色背景/摄影棚/白墙
- 所有场景在同一实景环境中（禁止咖啡馆/红砖墙/水泥墙）
- 同一环境内不同区域变化
## LOGO 要求
- 商品上的品牌商标必须在每个场景中自然可见
- 至少一个特写镜头聚焦商标
## 对白
自然口语化，像朋友推荐
输出 JSON 结构：
{{
  "title": "...", "product": "...", "genre": "带货/评测/好物推荐", "theme": "...",
  "showcase_style": "story", "visual_style": "{product.visual_style}",
  "setting": "统一场景环境描述",
  "characters": [{{"name": "...", "role": "...", "description": "..."}}],
  "scenes": [{{"scene": 1, "location": "...", "narration": "...", "dialogues": [], "product_focus": "...", "shot_type": "中景", "duration_seconds": 2}}],
  "duration_estimate": 15, "tags": [], "cta": "行动号召"
}}"""


@router.post("/generate-script", status_code=201)
def generate_ad_script(body: ProductInfoRequest, db: Session = Depends(get_db)):
    """生成带货剧本。

    如果已存在同商品草稿（ad_id 可选），则更新而非新建。
    如果 body 中带 ad_id，则复用已有的 ProductAd 记录。
    """
    if not body.name and not body.description:
        raise HTTPException(status_code=400, detail="请提供商品名称或描述")

    script_data = _generate_ad_script(body)

    # 检查是否有 ad_id 参数（复用已有草稿）
    ad_id = getattr(body, "ad_id", None)
    if ad_id:
        ad = db.query(ProductAd).filter(ProductAd.id == ad_id).first()
        if ad:
            ad.title = script_data.get("title", body.name or "商品带货视频")
            ad.product_info = json.dumps(body.model_dump(), ensure_ascii=False)
            ad.photo_ids = json.dumps(body.photo_ids, ensure_ascii=False)
            ad.script_content = json.dumps(script_data, ensure_ascii=False)
            ad.genre = script_data.get("genre", "带货")
            ad.status = "draft"
            ad.tags = ",".join(script_data.get("tags", [])) if isinstance(script_data.get("tags"), list) else "带货"
            ad.script_confirmed = False
            db.commit()
            db.refresh(ad)
            logger.info(f"Ad script updated (existing): id={ad.id}")
            return ad

    ad = ProductAd(
        title=script_data.get("title", body.name or "商品带货视频"),
        product_info=json.dumps(body.model_dump(), ensure_ascii=False),
        photo_ids=json.dumps(body.photo_ids, ensure_ascii=False),
        script_content=json.dumps(script_data, ensure_ascii=False),
        genre=script_data.get("genre", "带货"),
        status="draft",
        tags=",".join(script_data.get("tags", [])) if isinstance(script_data.get("tags"), list) else "带货",
    )
    db.add(ad)
    db.commit()
    db.refresh(ad)
    logger.info(f"Ad script created: id={ad.id}, title={ad.title}")

    # 自动评审
    try:
        showcase = script_data.get("showcase_style", "story")
        if showcase == "visual":
            ad.review_score = 9.0
            db.commit()
        else:
            from app.services.script_writer import auto_review_loop
            loop_result = auto_review_loop(script_data)
            final_script = loop_result["script"]
            ad.script_content = json.dumps(final_script, ensure_ascii=False)
            ad.title = final_script.get("title", ad.title)
            ad.review_score = loop_result["review"].get("overall_score")
            db.commit()
    except Exception:
        logger.exception(f"Auto review failed for ad {ad.id}")

    db.refresh(ad)
    return ad


@router.post("/{ad_id}/retry-script")
def retry_ad_script(ad_id: int, body: ScriptRetryRequest = None, db: Session = Depends(get_db)):
    """根据用户反馈重新生成带货剧本。"""
    from app.services.deepseek_client import chat_json

    ad = db.query(ProductAd).filter(ProductAd.id == ad_id).first()
    if not ad:
        raise HTTPException(status_code=404, detail="带货剧本不存在")

    feedback = (body or ScriptRetryRequest(ad_id=ad_id)).feedback or ""
    ad.script_user_feedback = feedback
    db.commit()

    # 重新调用 DeepSeek 生成
    product_info = json.loads(ad.product_info) if isinstance(ad.product_info, str) else {}
    photo_ids = json.loads(ad.photo_ids) if isinstance(ad.photo_ids, str) else []

    # 使用合成后的照片
    if ad.composite_confirmed and ad.composite_photo_ids:
        try:
            composite_ids = json.loads(ad.composite_photo_ids)
            photo_ids = composite_ids + [p for p in photo_ids if not any(kw in p.lower() for kw in ["logo", "label", "商标", "标", "tag"])]
        except Exception:
            pass

    req = ProductInfoRequest(
        name=product_info.get("name", ""),
        category=product_info.get("category", ""),
        description=product_info.get("description", ""),
        selling_points=product_info.get("selling_points", ""),
        target_audience=product_info.get("target_audience", ""),
        style_preference=product_info.get("style_preference", ""),
        photo_ids=photo_ids,
        visual_style=product_info.get("visual_style", "realistic"),
        showcase_style=product_info.get("showcase_style", "story"),
    )
    script_data = _generate_ad_script(req, user_feedback=feedback)

    ad.script_content = json.dumps(script_data, ensure_ascii=False)
    ad.script_confirmed = False
    db.commit()
    db.refresh(ad)
    logger.info(f"Ad script retry done: id={ad_id}")
    return ad


@router.post("/{ad_id}/confirm-script")
def confirm_ad_script(ad_id: int, db: Session = Depends(get_db)):
    """确认带货剧本。"""
    ad = db.query(ProductAd).filter(ProductAd.id == ad_id).first()
    if not ad:
        raise HTTPException(status_code=404, detail="带货剧本不存在")
    ad.script_confirmed = True
    db.commit()
    logger.info(f"Script confirmed for ad {ad_id}")
    return {"message": "剧本已确认", "ad_id": ad_id}


# ==============================================================
# 生成视频（步骤 3）
# ==============================================================

@router.post("/{ad_id}/generate-video")
def generate_ad_video(ad_id: int, resolution: str = "720p", db: Session = Depends(get_db)):
    """生成带货视频（要求剧本已确认）。"""
    ad = db.query(ProductAd).filter(ProductAd.id == ad_id).first()
    if not ad:
        raise HTTPException(status_code=404, detail="带货剧本不存在")

    if ad.status == "video_done":
        return {"message": "视频已存在", "ad_id": ad_id, "video_path": ad.video_path}

    if not ad.script_confirmed:
        raise HTTPException(status_code=400, detail="请先确认剧本")

    def _run():
        from app.database import SessionLocal
        _db = SessionLocal()
        try:
            _do_generate_ad_video_with_review(_db, ad_id, resolution)
        except Exception as e:
            logger.exception(f"Ad video generation failed: {e}")
        finally:
            _db.close()

    threading.Thread(target=_run, daemon=True).start()
    return {"message": "自动评审+生成视频已触发", "ad_id": ad_id}


def _do_generate_ad_video_with_review(db, ad_id: int, resolution: str = "720p"):
    from app.services.script_writer import auto_review_loop
    ad = db.query(ProductAd).filter(ProductAd.id == ad_id).first()
    if not ad:
        return
    logger.info(f"Starting auto-review for ad {ad_id}")

    script_data = json.loads(ad.script_content) if isinstance(ad.script_content, str) else ad.script_content
    showcase_style = script_data.get("showcase_style", "story") if isinstance(script_data, dict) else "story"

    if showcase_style == "visual":
        final_script = script_data
        loop_result = {"review": {"overall_score": 9.0, "summary": "视觉展示模式", "ready_for_video": True}, "iterations": 0, "achieved_target": True}
    else:
        loop_result = auto_review_loop(script_data)
        final_script = loop_result["script"]

    ad.script_content = json.dumps(final_script, ensure_ascii=False)
    ad.title = final_script.get("title", ad.title)
    ad.review_score = loop_result["review"].get("overall_score")
    db.commit()

    _do_generate_ad_video(db, ad, resolution, script_data_override=final_script)


def _do_generate_ad_video(db, ad: ProductAd, resolution: str = "720p", script_data_override: dict = None):
    from app.services.seedance_client import seedance_client, SeedanceError

    ad.status = "generating_video"
    db.commit()

    script_data = script_data_override or (json.loads(ad.script_content) if isinstance(ad.script_content, str) else ad.script_content)
    visual_style = script_data.get("visual_style", "realistic") if isinstance(script_data, dict) else "realistic"

    # 使用合成后的照片作为参考图（优先 composite_photo_ids）
    photo_ids = []
    if ad.composite_confirmed and ad.composite_photo_ids:
        try:
            photo_ids = json.loads(ad.composite_photo_ids)
        except Exception:
            pass
    if not photo_ids:
        photo_ids = json.loads(ad.photo_ids) if isinstance(ad.photo_ids, str) else (ad.photo_ids or [])

    raw_scenes = script_data.get("scenes") or script_data.get("script") or []
    scenes = raw_scenes if isinstance(raw_scenes, list) else []
    showcase_style = script_data.get("showcase_style", "story")

    reference_urls = []
    for pid in photo_ids:
        if not pid:
            continue
        if PUBLIC_URL:
            reference_urls.append(_photo_url(pid))
        else:
            img_path = os.path.join(PRODUCT_PHOTO_DIR, pid)
            if os.path.exists(img_path):
                import base64
                with open(img_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                ext = os.path.splitext(pid)[1].lower() or ".jpg"
                mime = "image/png" if ext == ".png" else "image/jpeg"
                reference_urls.append(f"data:{mime};base64,{b64}")
            else:
                logger.warning(f"  Ref image not found: {img_path}")

    logger.info(f"Creating Seedance ad video for ad {ad.id}, ref images: {len(reference_urls)}")

    if not os.environ.get("SEEDANCE_API_KEY"):
        ad.status = "video_failed"
        ad.error_message = "SEEDANCE_API_KEY 未配置"
        db.commit()
        return

    video_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "uploads", "comic_videos",
    )
    os.makedirs(video_dir, exist_ok=True)
    output_path = os.path.join(video_dir, f"ad_{ad.id}_{datetime.utcnow():%Y%m%d_%H%M%S}.mp4")

    SEGMENT_DURATION = 15

    image_desc_snippet = ""
    if isinstance(script_data, dict):
        raw_desc = script_data.get("image_description", "")
        if raw_desc:
            image_desc_snippet = raw_desc[:500]

    ref_instruction = (
        "CRITICAL: The generated video MUST strictly match the reference images. "
        "The product's appearance, color, shape, texture, material, logo, and all visible details "
        "in the video must be identical to the uploaded reference photos. "
        "The brand logo/trademark visible in the reference images MUST appear on the product "
        "at the exact same position. Do NOT alter or reimagine the product. "
    )

    style_prefix = (
        ref_instruction + "Cinematic product showcase video, professional model, multi-angle shoot, natural lighting, high quality, 4K, fashion photography style. "
    ) if visual_style == "realistic" else (
        ref_instruction + "2D anime fashion showcase, smooth animation, vibrant colors. "
    )

    if image_desc_snippet:
        style_prefix += f"Product appearance: {image_desc_snippet}. "

    scene_descs = []
    for s in scenes:
        angle = s.get("camera_angle", "")
        action = s.get("action", "")
        focus = s.get("product_focus", "")
        parts = [p for p in [angle, action, focus] if p]
        scene_descs.append(f"Scene {s.get('scene', '?')}: " + ", ".join(parts))
    combined_prompt = (style_prefix + ". ".join(scene_descs))[:2000]

    try:
        task = seedance_client.create_video_task(
            prompt=combined_prompt,
            duration=SEGMENT_DURATION,
            resolution=resolution,
            ratio="9:16",
            reference_images=reference_urls if reference_urls else None,
        )
        result = seedance_client.wait_for_completion(task["task_id"])
        if not result.get("video_url"):
            raise SeedanceError("No video_url returned")
        seedance_client.download_video(result["video_url"], output_path)
    except SeedanceError as e:
        ad.status = "video_failed"
        ad.error_message = str(e)
        db.commit()
        logger.error(f"Seedance failed for ad {ad.id}: {e}")
        return

    processed_path = output_path
    if script_data and isinstance(script_data, dict):
        if script_data.get("showcase_style", "story") != "visual":
            try:
                from app.services.video_postprocessor import postprocess_video
                processed = postprocess_video(output_path, script_data)
                if processed != output_path:
                    processed_path = processed
            except Exception as e:
                logger.exception(f"Post-processing failed: {e}")

    ad.video_path = processed_path
    ad.status = "video_done"
    db.commit()
    logger.info(f"Ad video done: id={ad.id}")


# ==============================================================
# 查询 & 删除
# ==============================================================

@router.get("/list", response_model=List[ProductAdScriptResponse])
def list_product_ads(
    status: Optional[str] = Query(None),
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    q = db.query(ProductAd).order_by(ProductAd.created_at.desc())
    if status:
        q = q.filter(ProductAd.status == status)
    return q.offset(skip).limit(limit).all()


@router.get("/{ad_id}", response_model=ProductAdScriptResponse)
def get_product_ad(ad_id: int, db: Session = Depends(get_db)):
    ad = db.query(ProductAd).filter(ProductAd.id == ad_id).first()
    if not ad:
        raise HTTPException(status_code=404, detail="带货剧本不存在")
    return ad


@router.delete("/{ad_id}")
def delete_product_ad(ad_id: int, db: Session = Depends(get_db)):
    ad = db.query(ProductAd).filter(ProductAd.id == ad_id).first()
    if not ad:
        raise HTTPException(status_code=404, detail="带货剧本不存在")
    db.delete(ad)
    db.commit()
    return {"message": "已删除", "ad_id": ad_id}
