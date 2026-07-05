import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from core.db import AsyncSessionLocal
from core.recurring_billing import generate_due_cycles


logger = logging.getLogger(__name__)
_scheduler: AsyncIOScheduler | None = None


async def _run_recurring_billing() -> None:
    async with AsyncSessionLocal() as db:
        try:
            generated_cycles = await generate_due_cycles(db)
            await db.commit()
            logger.info("Recurring billing cycle check complete. Generated %s cycle(s).", generated_cycles)
        except Exception:
            await db.rollback()
            logger.exception("Recurring billing cycle check failed")


def start_scheduler():
    global _scheduler

    if _scheduler and _scheduler.running:
        return _scheduler

    _scheduler = AsyncIOScheduler(timezone="Africa/Lagos")
    _scheduler.add_job(
        _run_recurring_billing,
        trigger=IntervalTrigger(hours=1),
        id="recurring_billing",
        replace_existing=True,
        max_instances=1,
        next_run_time=datetime.now(),
    )
    _scheduler.start()
    logger.info("Background recurring billing scheduler started.")
    return _scheduler
