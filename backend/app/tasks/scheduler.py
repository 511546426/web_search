"""定时任务调度器 — 用户手动开启后才执行定时抓取 + 生成."""
import logging
from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger("scheduler")

scheduler = BackgroundScheduler()
_job_id = "comic_daily_generate"


def _scrape_and_generate():
    """定时任务：抓取热点 → 生成剧本（不自动生成视频，等审核）."""
    try:
        from app.services.video_pipeline import run_batch_pipeline

        logger.info("Scheduled: scraping hot topics and generating scripts...")
        results = run_batch_pipeline(limit=2)
        for r in results:
            if r.success:
                logger.info(f"  OK: script_id={r.script_id}, video_id={r.video_id}")
            else:
                logger.error(f"  FAIL: {r.error}")
    except Exception:
        logger.exception("Scheduled task failed")


def start_scheduler():
    """启动调度器（仅启动服务，不注册定时任务，等待用户手动开启）. """
    scheduler.start()
    logger.info("Scheduler engine started (idle, no automatic jobs)")


def stop_scheduler():
    """停止调度器."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


def enable_auto_generate() -> bool:
    """用户开启定时自动生成（每天 8:07, 12:07, 18:07）. """
    if scheduler.get_job(_job_id):
        return True  # 已开启
    scheduler.add_job(
        _scrape_and_generate,
        trigger="cron",
        hour="8,12,18",
        minute="7",
        id=_job_id,
        name="每日漫剧自动生成",
    )
    logger.info("Auto generate ENABLED by user")
    return True


def disable_auto_generate() -> bool:
    """用户关闭定时自动生成."""
    if scheduler.get_job(_job_id):
        scheduler.remove_job(_job_id)
        logger.info("Auto generate DISABLED by user")
    return True


def is_auto_generate_enabled() -> bool:
    """检查定时自动生成是否开启."""
    return scheduler.get_job(_job_id) is not None
