from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from database import SessionLocal
from models import Trigger


async def claim_due_triggers() -> list[int]:
    """
    Due = active and next_check_at <= now, i.e. enough time
    (>= interval_seconds) has elapsed since the last check.

    Used by tasks.dispatch_due_triggers (Celery Beat's periodic tick).

    Claims by provisionally pushing next_check_at forward immediately,
    in the same transaction as the select — not just an optimization.
    With dispatch (Beat) and execution (worker) decoupled by the queue,
    a check that takes longer than one Beat tick (retries, a slow API)
    would otherwise still look "due" on the next tick and get dispatched
    a second time while the first is still running. The real completion
    value (worker.py, on success/failure/match) overwrites this placeholder
    once the check actually finishes — this only closes the race window
    in between.
    """
    now = datetime.now(timezone.utc)
    async with SessionLocal() as db:
        result = await db.execute(
            select(Trigger).where(Trigger.active.is_(True), Trigger.next_check_at <= now)
        )
        due = result.scalars().all()
        ids = [t.id for t in due]
        for trigger in due:
            trigger.next_check_at = now + timedelta(seconds=trigger.interval_seconds)
        await db.commit()
        return ids
