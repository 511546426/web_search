"""Coze 工作流专用 API — 供 Coze HTTP 插件调用，返回简洁 JSON."""
import os
import threading
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ComicScript, ComicVideo

logger = logging.getLogger("coze_api")

router = APIRouter(prefix="/api/v1", tags=["coze"])

PUBLIC_URL = os.environ.get("PUBLIC_URL", "").rstrip("/")


def _video_url(file_path: Optional[str]) -> Optional[str]:
    """将本地文件路径转为可访问的 URL."""
    if not file_path:
        return None
    if "uploads" in file_path:
        relative = file_path[file_path.index("uploads"):]
        return f"{PUBLIC_URL}/{relative}" if PUBLIC_URL else f"/{relative}"
    return None


@router.post("/generate")
def generate(
    topic: str,
    auto_generate_video: bool = False,
    db: Session = Depends(get_db),
):
    """接收话题 → 同步生成剧本 → 异步生成视频（可选）.

    Coze 工作流调用方式:
      1. POST /api/v1/generate?topic=xxx&auto_generate_video=true
         → 返回 { script_id, title, status }
      2. 轮询 GET /api/v1/status/{script_id} 直到 status=video_done
         → 拿到 video_url 用于发布
    """
    from app.services.video_pipeline import run_pipeline, generate_video_for_script

    # 同步生成剧本（~10-30s），不生成视频
    result = run_pipeline(topic=topic, auto_generate_video=False)
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error or "生成失败")

    script = db.query(ComicScript).filter(ComicScript.id == result.script_id).first()

    resp = {
        "script_id": result.script_id,
        "title": script.title if script else "",
        "status": "draft",
        "video_url": None,
        "message": "生成成功",
    }

    if auto_generate_video:
        resp["status"] = "generating_video"
        resp["message"] = "视频正在生成中，请轮询状态"

        def _run():
            try:
                generate_video_for_script(result.script_id)
            except Exception as e:
                logger.exception(f"Background video generation failed: {e}")

        threading.Thread(target=_run, daemon=True).start()

    return resp


@router.post("/generate-video/{script_id}")
def trigger_video(script_id: int, db: Session = Depends(get_db)):
    """为已有剧本触发视频生成（异步）。"""
    script = db.query(ComicScript).filter(ComicScript.id == script_id).first()
    if not script:
        raise HTTPException(status_code=404, detail="剧本不存在")

    if script.status == "video_done":
        video = db.query(ComicVideo).filter(
            ComicVideo.script_id == script_id,
            ComicVideo.status == "completed",
        ).first()
        return {
            "script_id": script_id,
            "status": "video_done",
            "video_url": _video_url(video.file_path) if video else None,
            "message": "视频已存在",
        }

    if script.status == "generating_video":
        return {"script_id": script_id, "status": "generating_video", "message": "视频正在生成中"}

    from app.services.video_pipeline import generate_video_for_script

    def _run():
        try:
            generate_video_for_script(script_id)
        except Exception as e:
            logger.exception(f"Background video generation failed: {e}")

    threading.Thread(target=_run, daemon=True).start()

    return {"script_id": script_id, "status": "generating_video", "message": "视频生成已触发"}


@router.get("/status/{script_id}")
def get_status(script_id: int, db: Session = Depends(get_db)):
    """查询生成状态 — Coze 轮询用。"""
    script = db.query(ComicScript).filter(ComicScript.id == script_id).first()
    if not script:
        raise HTTPException(status_code=404, detail="剧本不存在")

    video = db.query(ComicVideo).filter(
        ComicVideo.script_id == script_id,
        ComicVideo.status == "completed",
    ).first()

    return {
        "script_id": script.id,
        "title": script.title,
        "status": script.status,
        "video_url": _video_url(video.file_path) if video else None,
        "error_message": script.error_message,
        "created_at": script.created_at.isoformat() if script.created_at else None,
    }
