"""APScheduler background sync scheduler."""
import logging

from app.config import settings

logger = logging.getLogger(__name__)

_scheduler = None


def configure_scheduler():
    """Create and configure the APScheduler AsyncIOScheduler.

    Each sync job uses max_instances=1 to prevent concurrent runs of the same job.
    Only created when ENABLE_SYNC_SCHEDULER=true.
    """
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    scheduler = AsyncIOScheduler()

    # Airwallex: transactions every 30min, balance every 15min
    if settings.AIRWALLEX_CLIENT_ID and settings.AIRWALLEX_API_KEY:
        scheduler.add_job(
            _run_sync_job,
            "interval",
            minutes=30,
            id="airwallex_sync_transactions",
            args=["airwallex", "sync_transactions"],
            max_instances=1,
            replace_existing=True,
        )
        scheduler.add_job(
            _run_sync_job,
            "interval",
            minutes=15,
            id="airwallex_sync_balance",
            args=["airwallex", "sync_balance"],
            max_instances=1,
            replace_existing=True,
        )

    return scheduler


async def _run_sync_job(provider_name: str, capability: str) -> None:
    """Job function executed by APScheduler."""
    from app.database import AsyncSessionLocal
    from app.services.integration import run_sync
    import app.integrations.providers  # noqa: F401 — trigger registration

    logger.info("Running scheduled sync: %s/%s", provider_name, capability)
    async with AsyncSessionLocal() as db:
        try:
            result = await run_sync(db, provider_name, capability)
            await db.commit()
            logger.info(
                "Sync complete: %s/%s — inserted=%d skipped=%d errors=%d",
                provider_name,
                capability,
                result.get("inserted", 0),
                result.get("skipped", 0),
                result.get("errors", 0),
            )
        except Exception:
            await db.rollback()
            logger.exception("Scheduled sync failed: %s/%s", provider_name, capability)


def get_scheduler():
    """Return the global scheduler instance (None if not started)."""
    return _scheduler


async def start_scheduler() -> None:
    global _scheduler
    if not settings.ENABLE_SYNC_SCHEDULER:
        logger.info("Sync scheduler disabled (ENABLE_SYNC_SCHEDULER=false)")
        return
    _scheduler = configure_scheduler()
    _scheduler.start()
    logger.info("Sync scheduler started")


async def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Sync scheduler stopped")
