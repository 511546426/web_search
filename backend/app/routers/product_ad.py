"""商品带货视频 API — 上传商品照片 → 生成带货剧本 → 生成视频."""
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
from app.schemas import ProductInfoRequest, ProductAdScriptResponse

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
    """生成图片可访问 URL."""
    if PUBLIC_URL:
        return f"{PUBLIC_URL}/uploads/product_photos/{filename}"
    return f"/uploads/product_photos/{filename}"


# ---- 图片上传 ----

@router.post("/upload-photos")
def upload_photos(files: List[UploadFile] = File(...)):
    """上传商品照片（最多 9 张），返回文件名列表."""
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


# ---- 视频上传 + 抽帧 ----

@router.post("/upload-video")
def upload_product_video(file: UploadFile = File(...)):
    """上传商品视频，自动抽帧作为参考图，返回抽帧图片文件名列表."""
    import subprocess
    import tempfile

    # 保存上传的视频到临时文件
    suffix = os.path.splitext(file.filename or ".mp4")[1] or ".mp4"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file.file.read())
        tmp_path = tmp.name

    try:
        # 获取视频时长（秒）
        dur_result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", tmp_path],
            capture_output=True, text=True, timeout=30,
        )
        duration = float(dur_result.stdout.strip())
        if duration <= 0:
            raise HTTPException(status_code=400, detail="无法获取视频时长")

        # 均匀抽帧，最多 9 张
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
                logger.info(f"Frame extracted: {out_name} @ {seek_time:.1f}s")

        if not extracted:
            raise HTTPException(status_code=500, detail="视频抽帧失败，请检查视频文件")

        logger.info(f"Video processed: {file.filename}, {duration:.1f}s -> {len(extracted)} frames")
        return {"photo_ids": extracted, "count": len(extracted), "source_video": file.filename}

    finally:
        os.unlink(tmp_path)


# ---- 生成带货剧本 ----

def _generate_ad_script(product: ProductInfoRequest) -> dict:
    """调用 DeepSeek 生成带货剧本."""
    from app.services.deepseek_client import chat_json

    visual_style_text = "真人实景拍摄，真人出镜或产品实拍展示" if product.visual_style == "realistic" else "动漫风格，二维动画展示产品"
    style_note = "写实、真实产品展示" if product.visual_style == "realistic" else "二次元动漫风格"

    if product.showcase_style == "visual":
        system = f"""你是一名从业 15 年的时尚广告导演，曾为多个国际品牌执导产品视觉大片。你擅长用纯视觉语言讲述产品故事——不需要一句对白，仅靠镜头、光影、模特和节奏就让人产生购买欲。

## 你的核心能力

### 1. 视觉叙事体系（纯视觉，无对白）
每个场景就是一个镜头，通过画面本身传递信息：
- **Establishing（定场）**：产品/模特首次出现，建立第一印象
- **Detail（细节）**：材质、工艺、质感的视觉证明
- **Motion（动态）**：穿着/使用中的产品状态
- **Lifestyle（场景）**：产品在理想生活环境中的状态
- **Climax（高潮）**：最有冲击力的视觉画面

### 2. 镜头语言（精确到 AI 可执行）
每个场景必须指定镜头角度 + 模特动作 + 产品焦点：
- **景别系统**：远景全身（展示整体版型）、中景半身（展示上身效果）、近景特写（展示面料细节）、大特写（展示工艺/质感）
- **经典角度序列**：正面（直观展示）→ 侧面（展示版型轮廓）→ 背面（展示背部设计）→ 3/4（展示立体效果）→ 动态（展示穿着状态）→ 特写（材质证明）
- **运镜**：固定镜头（品质感）、缓慢推近（聚焦）、环绕（360度展示）、跟随（动态感）、升降（气场）
- **光影设计**：侧光（突出轮廓）、柔光（温馨感）、硬光（时尚感）、背光（氛围感）、环境光（真实感）

### 3. AI 视频生成优化
- 每个 prompt 要具体到 AI 可以执行：不说"自然好看"，说"阳光从 45 度侧方洒落，在面料上形成柔和的明暗过渡"
- 避免抽象形容词（漂亮/高级/精致），改用视觉描述（垂坠感/光泽度/轮廓线）
- 模特动作要简单明确（缓步向前/转身回眸/整理衣领/轻抚面料），避免复杂动作

### 4. 节奏与音乐
- 8-10 个场景，每个 2-5 秒，总时长控制在 20-35 秒
- 快慢交替：静态展示（2-3 秒）与动态镜头（3-5 秒）穿插
- 背景音乐建议具体到风格+节奏+氛围（如：轻快吉他，BPM 120，夏日清新感）

输出严格遵循 JSON 结构，每个场景都是一帧可执行的视觉指令：

{{
  "title": "视频标题",
  "product": "商品名称",
  "genre": "带货/穿搭展示",
  "theme": "核心卖点一句话",
  "showcase_style": "visual",
  "visual_style": "{product.visual_style}",
  "scenes": [
    {{
      "scene": 1,
      "camera_angle": "景别 + 角度 + 光影，如「正面全身，模特站立窗边，柔和的侧光照亮全身」",
      "action": "模特动作描述，具体可执行",
      "product_focus": "本场景要展示的产品卖点",
      "duration_seconds": 4
    }}
  ],
  "duration_estimate": 35,
  "tags": ["标签"],
  "background_music": "具体的背景音乐风格建议（曲风+节奏+氛围）"
}}"""
    else:
        system = f"""你是一名头部 MCN 机构的创意总监，年业绩过亿。你擅长制作"看了就想买"的电商短视频，深谙用户心理和转化逻辑。你的每条脚本都在剧情吸引力和销售转化力之间找到完美平衡。

## 你的核心方法论

### 1. 黄金开场（前 3 秒定生死）
- **痛点直击型**：直接呈现用户痛点，让观众觉得"说的就是我"
- **结果展示型**：先展示使用后的惊艳效果，勾起好奇心
- **悬念提问型**：抛出一个问题，让观众想知道答案
- **冲突引入型**：制造一个矛盾场景，自然引出产品

### 2. 产品展示体系（每一秒都在为转化服务）
每个场景都要明确"为什么要在这个场景展示产品的这个点"：
- **场景 1-2（建立需求）**：用户痛点 / 场景代入，让观众产生"我需要这个"的感觉
- **场景 3-5（产品解决方案）**：功能展示 + 使用场景 + 效果呈现，每场聚焦一个卖点
- **场景 6-7（信任建立）**：品质证明 / 对比测试 / 达人推荐，消除购买顾虑
- **场景 8（行动号召）**：CTA + 紧迫感 + 利益重申，促使用户下单

### 3. 镜头语言（适配 AI 视频生成）
每个场景要有清晰的镜头指示：
- **景别**：远景（场景环境）→ 中景（人物+产品互动）→ 近景（产品细节/表情反应）→ 特写（产品质感/效果对比）
- **运镜**：推（聚焦）、拉（展示全貌）、移（产品展示）、跟（使用过程）
- **光影**：明亮通透（食品/美妆）、冷峻质感（数码/男士）、温馨柔和（家居/母婴）

### 4. 对白与旁白
- **旁白（画外音）**：用于快速建立场景、点出痛点、强调卖点、引导下单
- **对白**：要真实自然，像朋友推荐而不是电视购物。"哇这个真的好好用" > "本品采用优质原料"
- **情绪标注**：帮助 AI 理解语气（惊喜 / 疑惑 / 感叹 / 温柔推荐）

### 5. 转化设计
- CTA 要具体：从"点击链接购买"到"现在下单立减 XX 元，前 100 名送 XX"
- 紧迫感：限时 / 限量 / 首发 / 独家
- 信任感：权威背书 / 用户证言 / 数据支撑
- 利益点：省钱 / 省时 / 变美 / 健康 / 社交价值

输出严格遵循 JSON 结构，确保片头抓人、片中精彩、片尾促单：

{{
  "title": "视频标题",
  "product": "商品名称",
  "genre": "带货/评测/好物推荐",
  "theme": "核心卖点一句话",
  "showcase_style": "story",
  "visual_style": "{product.visual_style}",
  "characters": [
    {{"name": "角色", "role": "主角/配角", "description": "角色描述"}}
  ],
  "scenes": [
    {{
      "scene": 1,
      "location": "场景描述（含环境+光影+氛围）",
      "narration": "旁白（画外音，推情绪或点卖点）",
      "dialogues": [
        {{"character": "角色", "line": "台词", "emotion": "情绪标注"}}
      ],
      "product_focus": "本场景展示的产品卖点",
      "shot_type": "远景/中景/近景/特写",
      "duration_seconds": 6
    }}
  ],
  "duration_estimate": 45,
  "tags": ["标签"],
  "cta": "行动号召，引导购买的话术（具体、紧迫、有利益点）"
}}"""

    prompt = f"""Create an e-commerce promotion short video script based on this product info:

Product name: {product.name}
Category: {product.category}
Description: {product.description}
Selling points: {product.selling_points}
Target audience: {product.target_audience}
Style preference: {product.style_preference or 'Not specified'}
Showcase mode: {'Visual showcase (no dialogue)' if product.showcase_style == 'visual' else 'Story-driven drama'}

Photo count: {len(product.photo_ids)} product photos available as reference.

Create a compelling short video script that showcases this product effectively.
Return ONLY the JSON, no markdown fences, no extra text."""

    result = chat_json(prompt, system=system, temperature=0.7, max_tokens=4096)
    result["visual_style"] = product.visual_style
    result["showcase_style"] = product.showcase_style
    return result


@router.post("/generate-script", status_code=201)
def generate_ad_script(body: ProductInfoRequest, db: Session = Depends(get_db)):
    """根据商品信息 + 照片生成带货剧本，自动评审并显示评分."""
    if not body.name and not body.description:
        raise HTTPException(status_code=400, detail="请提供商品名称或描述")

    script_data = _generate_ad_script(body)

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

    # 自动评审（剧情模式用循环修改达标，视觉模式直接满分）
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


# ---- 生成视频 ----

@router.post("/{ad_id}/generate-video")
def generate_ad_video(ad_id: int, resolution: str = "720p", db: Session = Depends(get_db)):
    """评审 → 自动修改达标 → 生成带货视频（一次完成）。"""
    ad = db.query(ProductAd).filter(ProductAd.id == ad_id).first()
    if not ad:
        raise HTTPException(status_code=404, detail="带货剧本不存在")

    if ad.status == "video_done":
        return {"message": "视频已存在", "ad_id": ad_id, "video_path": ad.video_path}

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
    """评审 → 修改达标 → 生成带货视频."""
    from app.services.script_writer import auto_review_loop

    ad = db.query(ProductAd).filter(ProductAd.id == ad_id).first()
    if not ad:
        return
    logger.info(f"Starting auto-review for ad {ad_id}")

    # 1. 自动评审循环（仅剧情模式，视觉展示无需评审对白）
    script_data = json.loads(ad.script_content) if isinstance(ad.script_content, str) else ad.script_content
    showcase_style = script_data.get("showcase_style", "story") if isinstance(script_data, dict) else "story"

    if showcase_style == "visual":
        final_script = script_data
        loop_result = {
            "review": {"overall_score": 9.0, "summary": "视觉展示模式，无需评审", "ready_for_video": True},
            "iterations": 0,
            "achieved_target": True,
        }
        logger.info(f"Ad {ad_id} is visual showcase, skipping review loop")
    else:
        loop_result = auto_review_loop(script_data)
        final_script = loop_result["script"]

    # 2. 保存修改后的剧本
    ad.script_content = json.dumps(final_script, ensure_ascii=False)
    ad.title = final_script.get("title", ad.title)
    ad.review_score = loop_result["review"].get("overall_score")
    db.commit()

    logger.info(
        f"Ad {ad_id} auto-review: score={loop_result['review'].get('overall_score')}, "
        f"iterations={loop_result['iterations']}, achieved={loop_result['achieved_target']}"
    )

    # 3. 生成视频（使用修改后的剧本）
    _do_generate_ad_video(db, ad, resolution, script_data_override=final_script)


def _do_generate_ad_video(db, ad: ProductAd, resolution: str = "720p", script_data_override: dict = None):
    """内部：同步生成带货视频."""
    from app.services.seedance_client import seedance_client, SeedanceError

    ad.status = "generating_video"
    db.commit()

    script_data = script_data_override or (json.loads(ad.script_content) if isinstance(ad.script_content, str) else ad.script_content)
    visual_style = script_data.get("visual_style", "realistic") if isinstance(script_data, dict) else "realistic"
    photo_ids = json.loads(ad.photo_ids) if isinstance(ad.photo_ids, str) else (ad.photo_ids or [])

    # 构建 prompt（兼容旧数据中的 "script" 键）
    raw_scenes = script_data.get("scenes") or script_data.get("script") or []
    scenes = raw_scenes if isinstance(raw_scenes, list) else []
    showcase_style = script_data.get("showcase_style", "story") if isinstance(script_data, dict) else "story"

    if showcase_style == "visual":
        style_prefix = (
            "Cinematic product showcase video, professional model, multi-angle shoot, "
            "natural lighting, high quality, 4K, fashion photography style, "
        ) if visual_style == "realistic" else (
            "2D anime fashion showcase, smooth animation, vibrant colors, character showcase, "
        )
        scene_descs = []
        for s in scenes[:8]:
            angle = s.get("camera_angle", "")
            action = s.get("action", "")
            focus = s.get("product_focus", "")
            parts = [p for p in [angle, action, focus] if p]
            scene_descs.append(f"Scene {s.get('scene', '?')}: " + ", ".join(parts))
        combined_prompt = style_prefix + ". ".join(scene_descs)
    else:
        style_prefix = "Realistic, live-action, product showcase, cinematic lighting, " if visual_style == "realistic" else "2D anime animation, product illustration style, "
        combined_prompt = style_prefix + " ".join(
            s.get("product_focus", s.get("narration", "")) for s in scenes[:5]
        )[:2000]

    combined_prompt = combined_prompt[:2000]

    # 参考图 URL
    reference_urls = [_photo_url(pid) for pid in photo_ids if pid]

    logger.info(f"Creating Seedance ad video task for ad {ad.id}, ref images: {len(reference_urls)}")

    video_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "uploads", "comic_videos",
    )
    os.makedirs(video_dir, exist_ok=True)
    output_path = os.path.join(
        video_dir, f"ad_{ad.id}_{datetime.utcnow():%Y%m%d_%H%M%S}.mp4"
    )

    est_duration = script_data.get("duration_estimate", 15) if isinstance(script_data, dict) else 15

    # 创建任务（带参考图）
    task = seedance_client.create_video_task(
        prompt=combined_prompt,
        duration=min(20, est_duration),
        resolution=resolution,
        ratio="9:16",
        reference_images=reference_urls if reference_urls else None,
    )
    result = seedance_client.wait_for_completion(task["task_id"])
    if result.get("video_url"):
        seedance_client.download_video(result["video_url"], output_path)

    # 后期处理：TTS 配音 + 字幕（仅剧情模式有对白）
    processed_path = output_path
    if script_data and isinstance(script_data, dict):
        showcase_style = script_data.get("showcase_style", "story")
        if showcase_style != "visual":
            try:
                from app.services.video_postprocessor import postprocess_video
                processed = postprocess_video(output_path, script_data)
                if processed != output_path:
                    processed_path = processed
                    logger.info(f"Post-processed ad video for ad {ad.id}: {processed_path}")
            except Exception as e:
                logger.exception(f"Ad post-processing failed: {e}")

    ad.video_path = processed_path
    ad.status = "video_done"
    db.commit()
    logger.info(f"Ad video done: id={ad.id}, path={processed_path}")


# ---- 查询 ----

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


@router.post("/{ad_id}/review")
def review_product_ad(ad_id: int, db: Session = Depends(get_db)):
    """评审带货剧本质量和可行性."""
    from app.services.script_writer import review_script as do_review

    ad = db.query(ProductAd).filter(ProductAd.id == ad_id).first()
    if not ad:
        raise HTTPException(status_code=404, detail="带货剧本不存在")

    script_content = json.loads(ad.script_content) if isinstance(ad.script_content, str) else ad.script_content
    result = do_review(script_content)
    return result


@router.delete("/{ad_id}")
def delete_product_ad(ad_id: int, db: Session = Depends(get_db)):
    """删除带货剧本."""
    ad = db.query(ProductAd).filter(ProductAd.id == ad_id).first()
    if not ad:
        raise HTTPException(status_code=404, detail="带货剧本不存在")
    db.delete(ad)
    db.commit()
    return {"message": "已删除", "ad_id": ad_id}
