"""视频生成流水线编排 — 串联抓取→剧本→分镜→视频生成."""
import os
import json
import logging
from datetime import datetime
from dataclasses import dataclass
from typing import Dict, List, Optional, Union

from dotenv import load_dotenv
from app.database import SessionLocal
from app.models import ComicScript, ComicVideo
from app.services.scraper import get_trending_topics
from app.services.script_writer import generate_script, generate_storyboard
from app.services.seedance_client import seedance_client, SeedanceError

logger = logging.getLogger("video_pipeline")

_ENV_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), ".env")
load_dotenv(_ENV_FILE)

_DEFAULT_UPLOADS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "uploads",
    "comic_videos",
)
UPLOADS_DIR = os.environ.get("VIDEO_OUTPUT_DIR", _DEFAULT_UPLOADS_DIR)


@dataclass
class PipelineResult:
    success: bool
    script_id: Optional[int] = None
    video_id: Optional[int] = None
    script: Optional[Dict] = None
    error: str = ""
    video_path: str = ""


def run_pipeline(
    topic: Union[Dict, str],
    auto_generate_video: bool = True,
    resolution: str = "720p",
) -> PipelineResult:
    """
    执行完整流水线：
    1. 生成剧本 (总是执行)
    2. 生成分镜
    3. 调用 Seedance 生成视频 (可选)
    """
    db = SessionLocal()
    try:
        if isinstance(topic, dict):
            topic_title = topic.get("title", "Untitled")
        else:
            topic_title = str(topic)

        logger.info(f"Generating script for: {topic_title}")
        script_data = generate_script(topic)

        storyboard = generate_storyboard(script_data)
        script_data["storyboard"] = storyboard

        db_script = ComicScript(
            title=script_data.get("title", topic_title),
            source_topic=json.dumps(topic, ensure_ascii=False) if isinstance(topic, dict) else topic_title,
            script_content=json.dumps(script_data, ensure_ascii=False),
            storyboard_json=json.dumps(storyboard, ensure_ascii=False),
            genre=script_data.get("genre", ""),
            status="draft",
            tags=json.dumps(script_data.get("tags", []), ensure_ascii=False),
        )
        db.add(db_script)
        db.commit()
        db.refresh(db_script)
        script_id = db_script.id
        logger.info(f"Script saved: id={script_id}, title={db_script.title}")

        result = PipelineResult(success=True, script_id=script_id, script=script_data)

        if auto_generate_video:
            try:
                video_result = _do_generate_video(db, db_script, storyboard, resolution)
                result.video_id = video_result.get("video_id")
                result.video_path = video_result.get("video_path", "")
            except SeedanceError as e:
                logger.error(f"Seedance error: {e}")
                db_script.status = "video_failed"
                db.commit()
                result.error = str(e)

        return result

    except Exception as e:
        logger.exception(f"Pipeline failed: {e}")
        return PipelineResult(success=False, error=str(e))
    finally:
        db.close()


def _do_generate_video(db, db_script: ComicScript, storyboard: List[Dict], resolution: str = "720p") -> dict:
    """内部：为已有 script 对象生成视频（同步）。"""
    db_script.status = "generating_video"
    db.commit()

    try:
        script_data = json.loads(db_script.script_content) if isinstance(db_script.script_content, str) else db_script.script_content
        est_duration = script_data.get("duration_estimate", 10) if isinstance(script_data, dict) else 10
        visual_style = script_data.get("visual_style", "anime") if isinstance(script_data, dict) else "anime"
    except (json.JSONDecodeError, AttributeError):
        est_duration = 10
        visual_style = "anime"

    style_prefix = "Realistic, live-action,真人影视, photorealistic, cinematic lighting, detailed textures, " if visual_style == "realistic" else "2D anime animation, manga art style, Japanese anime aesthetic, vibrant colors, clean lineart, "
    combined_prompt = style_prefix + " ".join(
        sb["video_prompt"] for sb in storyboard[:5]
    )[:2000]

    logger.info(f"Creating Seedance video task for script {db_script.id} (visual_style={visual_style})")
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    output_path = os.path.join(
        UPLOADS_DIR, f"video_{db_script.id}_{datetime.utcnow():%Y%m%d_%H%M%S}.mp4"
    )

    seedance_result = seedance_client.create_and_download(
        prompt=combined_prompt,
        output_path=output_path,
        duration=min(15, est_duration),
        resolution=resolution,
        ratio="9:16",
    )

    # 后期处理：TTS 配音 + 字幕
    try:
        processed_path = output_path
        script_data = json.loads(db_script.script_content) if isinstance(db_script.script_content, str) else db_script.script_content
        if isinstance(script_data, dict):
            from app.services.video_postprocessor import postprocess_video
            processed = postprocess_video(output_path, script_data)
            if processed != output_path:
                processed_path = processed
                logger.info(f"Post-processed video for script {db_script.id}: {processed_path}")
    except Exception as e:
        logger.exception(f"Post-processing failed for script {db_script.id}: {e}")
        processed_path = output_path

    db_video = ComicVideo(
        script_id=db_script.id,
        file_path=processed_path,
        seedance_task_id=seedance_result.get("task_id", ""),
        status="completed",
        duration_seconds=10,
        resolution=resolution,
        seedance_result=json.dumps(seedance_result, ensure_ascii=False),
    )
    db.add(db_video)
    db_script.status = "video_done"
    db.commit()
    db.refresh(db_video)

    logger.info(f"Video generated: id={db_video.id}, path={processed_path}")
    return {"video_id": db_video.id, "video_path": processed_path}


def generate_video_for_script(script_id: int, resolution: str = "720p") -> dict:
    """为已有剧本生成视频（独立使用，不创建新剧本）。

    返回: {"success": bool, "video_id": int|None, "error": str}
    """
    db = SessionLocal()
    try:
        script = db.query(ComicScript).filter(ComicScript.id == script_id).first()
        if not script:
            return {"success": False, "error": "剧本不存在"}

        if script.status == "video_done":
            existing = db.query(ComicVideo).filter(
                ComicVideo.script_id == script_id,
                ComicVideo.status == "completed",
            ).first()
            return {"success": True, "video_id": existing.id if existing else None}

        storyboard = json.loads(script.storyboard_json) if script.storyboard_json else []
        if not storyboard:
            # 没有分镜则从剧本重新生成
            script_content = json.loads(script.script_content)
            storyboard = generate_storyboard(script_content)
            script.storyboard_json = json.dumps(storyboard, ensure_ascii=False)
            db.commit()

        result = _do_generate_video(db, script, storyboard, resolution)
        return {"success": True, "video_id": result.get("video_id"), "error": ""}

    except SeedanceError as e:
        logger.error(f"Seedance error for script {script_id}: {e}")
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.exception(f"Video generation failed for script {script_id}: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()


def generate_video_for_script_with_review(script_id: int, resolution: str = "720p", target_score: float = 8.0) -> dict:
    """自动评审 + 反复修改直到达标 → 生成视频.

    返回: {"success": bool, "video_id": int|None, "review_result": dict, "error": str}
    """
    from app.services.script_writer import auto_review_loop

    db = SessionLocal()
    try:
        script = db.query(ComicScript).filter(ComicScript.id == script_id).first()
        if not script:
            return {"success": False, "error": "剧本不存在"}

        # 1. 自动评审循环
        script_content = json.loads(script.script_content) if isinstance(script.script_content, str) else script.script_content
        loop_result = auto_review_loop(script_content, target_score=target_score)

        # 2. 保存修改后的剧本
        final_script = loop_result["script"]
        script.script_content = json.dumps(final_script, ensure_ascii=False)
        script.title = final_script.get("title", script.title)
        script.review_score = loop_result["review"].get("overall_score")

        # 3. 重新生成分镜
        storyboard = generate_storyboard(final_script)
        script.storyboard_json = json.dumps(storyboard, ensure_ascii=False)
        db.commit()

        # 4. 生成视频
        video_result = _do_generate_video(db, script, storyboard, resolution)
        loop_result["review"]["iterations"] = loop_result["iterations"]
        loop_result["review"]["achieved_target"] = loop_result["achieved_target"]

        return {
            "success": True,
            "video_id": video_result.get("video_id"),
            "review_result": loop_result["review"],
            "iterations": loop_result["iterations"],
            "achieved_target": loop_result["achieved_target"],
            "error": "",
        }
    except SeedanceError as e:
        logger.error(f"Seedance error for script {script_id}: {e}")
        return {"success": False, "error": str(e), "review_result": None}
    except Exception as e:
        logger.exception(f"Video generation failed for script {script_id}: {e}")
        return {"success": False, "error": str(e), "review_result": None}
    finally:
        db.close()


def run_batch_pipeline(limit: int = 3) -> List[PipelineResult]:
    """批量处理：抓取热点 → 选题 → 逐个生成."""
    topics = get_trending_topics(limit=20)
    if not topics:
        return [PipelineResult(success=False, error="No trending topics found")]

    results = []
    for i, topic in enumerate(topics[:limit]):
        logger.info(f"Batch [{i+1}/{limit}]: {topic.get('title', 'N/A')}")
        result = run_pipeline(topic, auto_generate_video=True)
        results.append(result)
    return results
