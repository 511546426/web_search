"""漫剧视频管理 API."""
import os
import logging
import threading
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ComicScript, ComicVideo, PublishLog
from app.schemas import (
    ComicScriptResponse,
    ComicVideoResponse,
    PublishLogResponse,
    TriggerRequest,
    PublishRequest,
    TriggerBatchRequest,
)
from fastapi import Depends

router = APIRouter(prefix="/api/comic", tags=["comic_videos"])
logger = logging.getLogger("comic_videos")


# ---- 剧本 ----

@router.get("/scripts", response_model=List[ComicScriptResponse])
def list_scripts(
    status: Optional[str] = Query(None),
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    q = db.query(ComicScript).order_by(ComicScript.created_at.desc())
    if status:
        q = q.filter(ComicScript.status == status)
    return q.offset(skip).limit(limit).all()


@router.get("/scripts/{script_id}", response_model=ComicScriptResponse)
def get_script(script_id: int, db: Session = Depends(get_db)):
    s = db.query(ComicScript).filter(ComicScript.id == script_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="剧本不存在")
    return s


@router.post("/scripts/{script_id}/regenerate-video")
def regenerate_video(script_id: int, db: Session = Depends(get_db)):
    script = db.query(ComicScript).filter(ComicScript.id == script_id).first()
    if not script:
        raise HTTPException(status_code=404, detail="剧本不存在")

    from app.services.video_pipeline import run_pipeline

    topic = script.source_topic or script.title

    def _run():
        run_pipeline(topic, auto_generate_video=True)

    threading.Thread(target=_run, daemon=True).start()
    return {"message": "视频重新生成已触发", "script_id": script_id}


# ---- 触发生成 ----

@router.post("/trigger")
def trigger_pipeline(body: TriggerRequest):
    from app.services.video_pipeline import run_pipeline

    topic = body.topic or "最新热门话题"
    if body.topic:
        topic = {"title": body.topic, "platform": "manual"}

    def _run():
        run_pipeline(topic, auto_generate_video=body.auto_generate_video, resolution=body.resolution)

    threading.Thread(target=_run, daemon=True).start()
    return {"message": "视频生成流水线已触发", "topic": str(topic)}


@router.post("/trigger-batch")
def trigger_batch(body: TriggerBatchRequest):
    from app.services.video_pipeline import run_batch_pipeline

    def _run():
        run_batch_pipeline(limit=body.limit)

    threading.Thread(target=_run, daemon=True).start()
    return {"message": f"批量生成已触发，处理 {body.limit} 个热点"}


# ---- 视频 ----

@router.get("/videos", response_model=List[ComicVideoResponse])
def list_videos(
    status: Optional[str] = Query(None),
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    q = db.query(ComicVideo).order_by(ComicVideo.created_at.desc())
    if status:
        q = q.filter(ComicVideo.status == status)
    return q.offset(skip).limit(limit).all()


@router.get("/videos/{video_id}", response_model=ComicVideoResponse)
def get_video(video_id: int, db: Session = Depends(get_db)):
    v = db.query(ComicVideo).filter(ComicVideo.id == video_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="视频不存在")
    return v


# ---- 发布 ----

@router.post("/videos/{video_id}/publish")
def publish_video(video_id: int, body: PublishRequest, db: Session = Depends(get_db)):
    video = db.query(ComicVideo).filter(ComicVideo.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="视频不存在")

    script = db.query(ComicScript).filter(ComicScript.id == video.script_id).first()
    video_file = video.file_path or ""
    publish_url = ""
    publish_error = ""

    # B站：真正上传发布
    if body.platform == "bilibili":
        from app.services.bilibili_publisher import get_publisher, BilibiliError

        publisher = get_publisher()
        if not publisher:
            raise HTTPException(
                status_code=400,
                detail="B站发布未配置（缺少 BILIBILI_APP_KEY / APP_SECRET / REFRESH_TOKEN）",
            )

        try:
            # 获取视频文件内容（SMB 模式时从 Windows 共享读取）
            video_data = None
            if os.path.exists(video_file):
                with open(video_file, "rb") as f:
                    video_data = f.read()
            elif os.environ.get("SMB_HOST"):
                from app.services.smb_storage import smb_read
                video_data = smb_read(video_file)

            if not video_data:
                raise BilibiliError("视频文件不存在（既不在本地也不在 SMB 共享）")

            # 写入临时文件用于上传
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
                tmp.write(video_data)
                tmp_path = tmp.name

            try:
                title = script.title if script else f"视频 {video_id}"
                desc = body.message or f"AI 生成的漫剧视频 - {title}"
                result = publisher.publish(
                    file_path=tmp_path,
                    title=title,
                    description=desc,
                    tags=["漫剧", "AI视频", "AI生成"],
                )
                publish_url = result.get("url", "")
                if result.get("bvid"):
                    publish_error = ""
                else:
                    publish_error = "B站发布返回异常"
            finally:
                os.unlink(tmp_path)

        except Exception as e:
            logger.exception("Bilibili publish failed")
            raise HTTPException(status_code=502, detail=f"B站发布失败: {e}")
    else:
        # 其他平台（微博/抖音/微信）：仅记录
        pass

    log = PublishLog(
        video_id=video_id,
        platform=body.platform,
        status="published",
        publish_url=publish_url,
        publish_message=body.message,
        published_at=datetime.utcnow(),
    )
    db.add(log)

    if script:
        script.status = "published"

    db.commit()
    db.refresh(log)

    return {
        "message": f"已发布到 {body.platform}",
        "publish_id": log.id,
        "video_id": video_id,
        "publish_url": publish_url,
    }


@router.get("/publish-logs", response_model=List[PublishLogResponse])
def list_publish_logs(video_id: Optional[int] = Query(None), db: Session = Depends(get_db)):
    q = db.query(PublishLog).order_by(PublishLog.created_at.desc())
    if video_id:
        q = q.filter(PublishLog.video_id == video_id)
    return q.limit(50).all()


# ---- 热点查看 ----

@router.get("/trending")
def get_trending(limit: int = Query(15)):
    from app.services.scraper import get_trending_topics

    return get_trending_topics(limit=limit)


# ---- 统计 ----

@router.get("/stats")
def comic_stats(db: Session = Depends(get_db)):
    return {
        "total_scripts": db.query(ComicScript).count(),
        "total_videos": db.query(ComicVideo).count(),
        "videos_completed": db.query(ComicVideo).filter(ComicVideo.status == "completed").count(),
        "videos_failed": db.query(ComicVideo).filter(ComicVideo.status == "failed").count(),
        "total_published": db.query(PublishLog).filter(PublishLog.status == "published").count(),
        "scripts_by_status": {
            s: db.query(ComicScript).filter(ComicScript.status == s).count()
            for s in ["draft", "generating_video", "video_done", "video_failed", "published"]
        },
    }
