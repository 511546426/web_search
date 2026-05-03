"""定时任务调度器 — 自动抓取热点 + 生成剧本 + 生成视频."""
import logging
from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger("scheduler")

scheduler = BackgroundScheduler()


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
    """启动定时任务."""
    # 每天 8:07, 12:07, 18:07 自动抓取+生成（避开整点）
    scheduler.add_job(
        _scrape_and_generate,
        trigger="cron",
        hour="8,12,18",
        minute="7",
        id="comic_daily_generate",
        name="每日漫剧自动生成",
    )
    scheduler.start()
    logger.info("Scheduler started: daily comic generation at 8:07, 12:07, 18:07")


def stop_scheduler():
    """停止定时任务."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
