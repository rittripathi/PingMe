"""
tasks.py
---------
The actual background jobs Celery runs. There are two:

  1. check_all_triggers -- runs on Celery beat's schedule (every 60s). It
     does NOT check any prices itself; it just looks up every active
     trigger and fans out ONE job per trigger to check_single_trigger.
     This is the producer-consumer pattern: beat produces jobs, workers
     consume them, one at a time, possibly in parallel.

  2. check_single_trigger -- does the real work for ONE trigger: fetch the
     price, check the condition, notify if it fired, log the event. This
     calls the exact same trigger_service.run_trigger_check() function the
     manual POST /triggers/{id}/check endpoint uses.
"""

from app import models, trigger_service
from app.celery_app import celery_app
from app.database import get_db_session


@celery_app.task(name="app.tasks.check_all_triggers")
def check_all_triggers():
    """
    Runs every 60 seconds (see celery_app.py's beat_schedule).
    Finds every active trigger across every user, and queues an individual
    check_single_trigger job for each one -- it does not check any prices
    itself, it only fans the work out.
    """
    with get_db_session() as db:
        trigger_ids = [
            t.id for t in db.query(models.Trigger).filter(models.Trigger.is_active == True).all()
        ]

    for trigger_id in trigger_ids:
        check_single_trigger.delay(trigger_id)

    return f"queued {len(trigger_ids)} trigger check(s)"


@celery_app.task(name="app.tasks.check_single_trigger")
def check_single_trigger(trigger_id: int):
    """
    Checks ONE trigger: fetches the live price, evaluates the condition,
    sends a Telegram message if it fired, and logs the result -- identical
    behavior to manually calling POST /triggers/{id}/check, just triggered
    by the scheduler instead of a person clicking a button.
    """
    with get_db_session() as db:
        trigger = db.query(models.Trigger).filter(models.Trigger.id == trigger_id).first()
        if trigger is None or not trigger.is_active:
            return f"trigger {trigger_id} not found or inactive, skipped"

        user = db.query(models.User).filter(models.User.id == trigger.user_id).first()
        if user is None or not user.telegram_chat_id:
            return f"trigger {trigger_id}: owner has no Telegram connected, skipped"

        return trigger_service.run_trigger_check(trigger, user, db)


# ==============================================================================
# ROLE OF THIS FILE:
# Defines the two Celery tasks that make PingMe run automatically: one that
# fans "check everything" out into individual jobs, and one that actually
# checks a single trigger. Both reuse trigger_service.run_trigger_check()
# instead of duplicating the price-check-notify-log logic a third time.
# ==============================================================================