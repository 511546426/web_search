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


# ---- 生成带货剧本 ----

def _generate_ad_script(product: ProductInfoRequest) -> dict:
    """调用 DeepSeek 生成带货剧本."""
    from app.services.deepseek_client import chat_json

    visual_style_text = "真人实景拍摄，真人出镜或产品实拍展示" if product.visual_style == "realistic" else "动漫风格，二维动画展示产品"
    style_note = "写实、真实产品展示" if product.visual_style == "realistic" else "二次元动漫风格"

    system = f"""You are a professional e-commerce short video scriptwriter.
Create compelling product promotion short drama scripts in Chinese.

Style: {visual_style_text}
All visual descriptions must match {style_note} style.

Your output MUST be valid JSON with this structure:
{{
  "title": "视频标题",
  "product": "商品名称",
  "genre": "带货/评测/好物推荐",
  "theme": "核心卖点一句话",
  "characters": [
    {{"name": "角色", "role": "主角/配角", "description": "角色描述"}}
  ],
  "script": [
    {{
      "scene": 1,
      "location": "场景描述",
      "narration": "旁白",
      "dialogues": [
        {{"character": "角色", "line": "台词", "emotion": "情绪"}}
      ],
      "product_focus": "本场景如何展示产品"
    }}
  ],
  "duration_estimate": 45,
  "tags": ["标签"],
  "cta": "行动号召，引导购买的话术"
}}

Keep scenes between 4-8, make it fast-paced and suitable for vertical video (9:16).
Focus on product benefits, user pain points, and emotional triggers."""

    prompt = f"""Create an e-commerce promotion short video script based on this product info:

Product name: {product.name}
Category: {product.category}
Description: {product.description}
Selling points: {product.selling_points}
Target audience: {product.target_audience}
Style preference: {product.style_preference or 'Not specified'}

Photo count: {len(product.photo_ids)} product photos available as reference.

Create a compelling short video script that showcases this product effectively.
Return ONLY the JSON, no markdown fences, no extra text."""

    result = chat_json(prompt, system=system, temperature=0.7, max_tokens=4096)
    result["visual_style"] = product.visual_style
    return result


@router.post("/generate-script", response_model=ProductAdScriptResponse, status_code=201)
def generate_ad_script(body: ProductInfoRequest, db: Session = Depends(get_db)):
    """根据商品信息 + 照片生成带货剧本."""
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

    # 1. 自动评审循环
    script_data = json.loads(ad.script_content) if isinstance(ad.script_content, str) else ad.script_content
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

    # 构建 prompt
    scenes = script_data.get("script", []) if isinstance(script_data, dict) else []
    style_prefix = "Realistic, live-action, product showcase, cinematic lighting, " if visual_style == "realistic" else "2D anime animation, product illustration style, "
    combined_prompt = style_prefix + " ".join(
        s.get("product_focus", s.get("narration", "")) for s in scenes[:5]
    )[:2000]

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

    ad.video_path = output_path
    ad.status = "video_done"
    db.commit()
    logger.info(f"Ad video done: id={ad.id}, path={output_path}")


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
