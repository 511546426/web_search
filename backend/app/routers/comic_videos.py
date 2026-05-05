"""漫剧视频管理 API."""
import json
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
    CreateScriptRequest,
    PublishLogResponse,
    ScriptFromTextRequest,
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


@router.delete("/scripts/{script_id}")
def delete_script(script_id: int, db: Session = Depends(get_db)):
    """删除剧本及其关联视频."""
    s = db.query(ComicScript).filter(ComicScript.id == script_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="剧本不存在")
    db.query(ComicVideo).filter(ComicVideo.script_id == script_id).delete()
    db.delete(s)
    db.commit()
    return {"message": "已删除", "script_id": script_id}


@router.post("/scripts/{script_id}/review")
def review_script(script_id: int, db: Session = Depends(get_db)):
    """评审剧本质量和可行性."""
    from app.services.script_writer import review_script as do_review

    s = db.query(ComicScript).filter(ComicScript.id == script_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="剧本不存在")

    script_content = json.loads(s.script_content) if isinstance(s.script_content, str) else s.script_content
    result = do_review(script_content)
    return result


@router.post("/scripts", response_model=ComicScriptResponse, status_code=201)
def create_script(body: CreateScriptRequest, db: Session = Depends(get_db)):
    """手动创建剧本（自己提供内容，不经过 AI 生成）。"""
    script = ComicScript(
        title=body.title,
        source_topic=body.source_topic,
        script_content=body.script_content,
        genre=body.genre or "",
        status="draft",
        tags=body.tags or "",
    )
    db.add(script)
    db.commit()
    db.refresh(script)
    logger.info(f"Manual script created: id={script.id}, title={script.title}")
    return script


@router.post("/scripts/from-text", status_code=201)
def create_script_from_text(body: ScriptFromTextRequest, db: Session = Depends(get_db)):
    """提供纯文本剧本，自动解析为结构化 JSON 并保存，同时自动评审。"""
    from app.services.script_writer import format_raw_script, review_script

    parsed = format_raw_script(body.text, visual_style=body.visual_style)
    script_content = json.dumps(parsed, ensure_ascii=False)

    script = ComicScript(
        title=parsed.get("title", "未命名剧本"),
        source_topic=body.source_topic or parsed.get("theme", ""),
        script_content=script_content,
        genre=parsed.get("genre", ""),
        status="draft",
        tags=",".join(parsed.get("tags", [])) if isinstance(parsed.get("tags"), list) else "",
    )
    db.add(script)
    db.commit()
    db.refresh(script)
    logger.info(f"Script created from text: id={script.id}, title={script.title}")

    # 自动评审循环（自动修改直到达标 ≥ 8 分）
    try:
        from app.services.script_writer import auto_review_loop

        loop_result = auto_review_loop(parsed)
        final_script = loop_result["script"]
        review_result = loop_result["review"]

        # 保存修改后的剧本
        script.script_content = json.dumps(final_script, ensure_ascii=False)
        script.title = final_script.get("title", script.title)
        script.review_score = review_result.get("overall_score")
        db.commit()

        summary = review_result.get("summary", "")
        iterations = loop_result["iterations"]
        if iterations > 1:
            summary += f"（自动修改 {iterations - 1} 轮后达标）"
    except Exception:
        review_result = {"overall_score": None, "summary": "评审失败", "ready_for_video": False}

    return {
        "id": script.id,
        "title": script.title,
        "status": script.status,
        "genre": script.genre,
        "tags": script.tags,
        "created_at": script.created_at.isoformat(),
        "updated_at": script.updated_at.isoformat() if script.updated_at else None,
        "review_score": review_result.get("overall_score"),
        "review_summary": review_result.get("summary", ""),
        "review_ready": review_result.get("ready_for_video", False),
    }


@router.post("/scripts/{script_id}/regenerate-video")
def regenerate_video(script_id: int, db: Session = Depends(get_db)):
    """旧版：直接生成视频（无评审）。"""
    script = db.query(ComicScript).filter(ComicScript.id == script_id).first()
    if not script:
        raise HTTPException(status_code=404, detail="剧本不存在")

    from app.services.video_pipeline import run_pipeline

    topic = script.source_topic or script.title

    def _run():
        run_pipeline(topic, auto_generate_video=True)

    threading.Thread(target=_run, daemon=True).start()
    return {"message": "视频重新生成已触发", "script_id": script_id}


@router.post("/scripts/{script_id}/generate-video")
def generate_video_with_review(script_id: int, db: Session = Depends(get_db)):
    """评审 → 自动修改达标 → 生成视频（一次完成）。"""
    script = db.query(ComicScript).filter(ComicScript.id == script_id).first()
    if not script:
        raise HTTPException(status_code=404, detail="剧本不存在")

    from app.services.video_pipeline import generate_video_for_script_with_review

    def _run():
        try:
            result = generate_video_for_script_with_review(script_id)
            if result.get("success"):
                logger.info(
                    f"Script {script_id} auto-review+generate done: "
                    f"score={result.get('review_result', {}).get('overall_score', '?')}, "
                    f"iterations={result.get('iterations')}"
                )
            if result.get("review_result"):
                review = result["review_result"]
                logger.info(
                    f"Script {script_id} auto-review: score={review.get('overall_score')}, "
                    f"iterations={result.get('iterations')}, achieved={result.get('achieved_target')}"
                )
            if not result.get("success"):
                logger.error(f"Generate failed for script {script_id}: {result.get('error')}")
        except Exception as e:
            logger.exception(f"Auto review+generate failed for script {script_id}: {e}")

    threading.Thread(target=_run, daemon=True).start()
    return {
        "message": "自动评审+生成视频已触发，完成后将通知",
        "script_id": script_id,
    }


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


@router.delete("/videos/{video_id}")
def delete_video(video_id: int, db: Session = Depends(get_db)):
    """删除视频记录."""
    v = db.query(ComicVideo).filter(ComicVideo.id == video_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="视频不存在")
    db.delete(v)
    db.commit()
    return {"message": "已删除", "video_id": video_id}


# ---- B站登录 ----

@router.get("/bilibili/login")
def bilibili_login_status():
    """查看B站登录状态。"""
    from app.services.bilibili_publisher import get_publisher

    pub = get_publisher()
    return {"logged_in": pub.is_logged_in and pub.check_login_valid()}


@router.post("/bilibili/login")
def bilibili_login():
    """生成B站登录二维码。"""
    from app.services.bilibili_publisher import generate_qrcode_login

    upload_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "uploads"
    )
    result = generate_qrcode_login(output_dir=upload_dir)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return {
        "qr_image_url": "/uploads/bilibili_qrcode.png",
        "message": "请用B站手机APP扫描二维码登录",
    }


@router.get("/bilibili/login/check")
def bilibili_login_check():
    """检查二维码扫码状态。"""
    from app.services.bilibili_publisher import check_qrcode_login

    return check_qrcode_login()


# ---- 发布 ----

@router.post("/videos/{video_id}/publish")
def publish_video(video_id: int, body: PublishRequest, db: Session = Depends(get_db)):
    video = db.query(ComicVideo).filter(ComicVideo.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="视频不存在")

    script = db.query(ComicScript).filter(ComicScript.id == video.script_id).first()
    video_file = video.file_path or ""
    publish_url = ""
    publish_message = body.message or ""
    is_draft = False

    # B站：真正上传发布
    result = {}
    if body.platform == "bilibili":
        from app.services.bilibili_publisher import get_publisher, BilibiliError

        publisher = get_publisher()
        if not publisher.is_logged_in:
            raise HTTPException(
                status_code=400,
                detail="B站未登录，请先扫码登录（点上方B站扫码登录按钮）",
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
                publish_message = result.get("message", body.message or "")
                is_draft = result.get("draft", False)
            finally:
                os.unlink(tmp_path)

        except Exception as e:
            logger.exception("Bilibili publish failed")
            raise HTTPException(status_code=502, detail=f"B站发布失败: {e}")

    log = PublishLog(
        video_id=video_id,
        platform=body.platform,
        status="draft" if is_draft else "published",
        publish_url=publish_url,
        publish_message=publish_message,
        published_at=datetime.utcnow(),
    )
    db.add(log)

    if script and result.get("draft"):
        script.status = "draft"

    db.commit()
    db.refresh(log)

    resp = {
        "message": publish_message or f"已发布到 {body.platform}",
        "publish_id": log.id,
        "video_id": video_id,
        "publish_url": publish_url,
    }
    if is_draft:
        resp["draft"] = True
        resp["draft_url"] = publish_url
    return resp


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


# ---- 定时任务开关 ----

@router.get("/scheduler/status")
def scheduler_status():
    """查看定时自动生成是否开启."""
    from app.tasks.scheduler import is_auto_generate_enabled
    return {"enabled": is_auto_generate_enabled()}


@router.post("/scheduler/enable")
def scheduler_enable():
    """开启定时自动生成（每天 8:07, 12:07, 18:07 抓取热点 + 生成剧本）. """
    from app.tasks.scheduler import enable_auto_generate
    enable_auto_generate()
    logger.info("Auto generate enabled by user")
    return {"message": "定时自动生成已开启", "enabled": True}


@router.post("/scheduler/disable")
def scheduler_disable():
    """关闭定时自动生成."""
    from app.tasks.scheduler import disable_auto_generate
    disable_auto_generate()
    logger.info("Auto generate disabled by user")
    return {"message": "定时自动生成已关闭", "enabled": False}
