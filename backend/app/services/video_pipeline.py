"""视频生成流水线编排 — 串联抓取→剧本→分镜→视频生成."""
import os
import json
import logging
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union

from app.database import SessionLocal
from app.models import ComicScript, ComicVideo
from app.services.scraper import get_trending_topics
from app.services.script_writer import generate_script, generate_storyboard
from app.services.seedance_client import seedance_client, SeedanceError

logger = logging.getLogger("video_pipeline")

UPLOADS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "uploads",
    "comic_videos",
)


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
        # Step 1: 生成剧本
        if isinstance(topic, dict):
            topic_title = topic.get("title", "Untitled")
        else:
            topic_title = str(topic)

        logger.info(f"Generating script for: {topic_title}")
        script_data = generate_script(topic)

        # Step 2: 生成分镜
        storyboard = generate_storyboard(script_data)
        script_data["storyboard"] = storyboard

        # Step 3: 保存剧本到数据库
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

        # Step 4: 生成视频 (可选)
        if auto_generate_video:
            try:
                db_script.status = "generating_video"
                db.commit()

                # 使用全部场景的 prompt 拼接，并明确指定动漫风格
                style_prefix = "2D anime animation, manga art style, Japanese anime aesthetic, vibrant colors, clean lineart, "
                combined_prompt = style_prefix + " ".join(
                    sb["video_prompt"] for sb in storyboard[:5]
                )[:2000]

                logger.info(f"Creating Seedance video task for script {script_id}")
                os.makedirs(UPLOADS_DIR, exist_ok=True)
                output_path = os.path.join(
                    UPLOADS_DIR, f"video_{script_id}_{datetime.utcnow():%Y%m%d_%H%M%S}.mp4"
                )

                seedance_result = seedance_client.create_and_download(
                    prompt=combined_prompt,
                    output_path=output_path,
                    duration=min(15, script_data.get("duration_estimate", 10)),
                    resolution=resolution,
                    ratio="9:16",
                )

                # 保存视频记录
                db_video = ComicVideo(
                    script_id=script_id,
                    file_path=output_path,
                    seedance_task_id=seedance_result.get("task_id", ""),
                    status="completed",
                    duration_seconds=script_data.get("duration_estimate", 10),
                    resolution=resolution,
                    seedance_result=json.dumps(seedance_result, ensure_ascii=False),
                )
                db.add(db_video)
                db_script.status = "video_done"
                db.commit()
                db.refresh(db_video)

                result.video_id = db_video.id
                result.video_path = output_path
                logger.info(f"Video generated: id={db_video.id}, path={output_path}")

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
