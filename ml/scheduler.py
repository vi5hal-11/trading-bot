"""
APScheduler wrapper for weekly ML retraining and daily Telegram digests.
Runs as an asyncio background job inside main.py's event loop.
"""
from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config.settings import Settings
from ml.retrain import run_retrain


async def _retrain_job(settings: Settings, storage, telegram):
    logger.info("Scheduled retrain job triggered")
    try:
        await run_retrain(settings, storage, telegram)
    except Exception as e:
        logger.error(f"Scheduled retrain failed: {e}")


async def _daily_digest_job(bot_state, telegram):
    try:
        if bot_state.paper_trader:
            summary = bot_state.paper_trader.summary()
            await telegram.send_daily_digest(summary)
    except Exception as e:
        logger.warning(f"Daily digest failed: {e}")


async def _eod_recap_job(bot_state, telegram):
    try:
        if bot_state.paper_trader:
            summary = bot_state.paper_trader.summary()
            await telegram.send_daily_digest(summary)
            logger.info("End-of-day recap sent")
    except Exception as e:
        logger.warning(f"EOD recap failed: {e}")


def build_scheduler(settings: Settings, storage, telegram,
                    bot_state=None) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")

    day = getattr(settings, "retrain_day_of_week", "sun")
    hour = getattr(settings, "retrain_hour", 2)

    scheduler.add_job(
        _retrain_job,
        trigger="cron",
        day_of_week=day,
        hour=hour,
        minute=0,
        args=[settings, storage, telegram],
        id="weekly_retrain",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    if bot_state is not None:
        scheduler.add_job(
            _daily_digest_job,
            trigger="cron",
            hour=0,
            minute=5,
            args=[bot_state, telegram],
            id="daily_digest",
            replace_existing=True,
        )
        scheduler.add_job(
            _eod_recap_job,
            trigger="cron",
            hour=23,
            minute=55,
            args=[bot_state, telegram],
            id="eod_recap",
            replace_existing=True,
        )

    logger.info(f"Retrain scheduler configured | day={day} hour={hour:02d}:00 UTC | daily digest 00:05 + 23:55 UTC")
    return scheduler
