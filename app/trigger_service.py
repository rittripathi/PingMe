"""
trigger_service.py
--------------------
The shared "check one trigger" logic -- fetch the price, check the
condition, notify if it fired, log the result.

This code used to live directly inside the /triggers/{id}/check endpoint.
Now that Celery needs to run the SAME logic on a schedule, it's been pulled
out here so there's only ONE place this logic can go wrong -- both the
manual endpoint and the automatic background job call this same function.
"""

from sqlalchemy.orm import Session

from app import models, notifier, price_service


def run_trigger_check(trigger: models.Trigger, user: models.User, db: Session) -> dict:
    """
    Runs one trigger's check against the live price, notifies the owning
    user on Telegram if it fired, and logs a TriggerEvent either way.
    Returns a small summary dict -- useful both as an API response and as
    a Celery task result you can inspect later.
    """
    current_price = price_service.get_current_price(trigger.asset)
    fired = price_service.condition_met(current_price, trigger.condition, trigger.target_value)

    if fired:
        message = (
            f"PingMe alert: {trigger.asset} is now {current_price} "
            f"(condition: {trigger.condition} {trigger.target_value})"
        )
        notifier.send_telegram_message(user.telegram_chat_id, message)

    event = models.TriggerEvent(
        trigger_id=trigger.id,
        checked_value=current_price,
        fired=fired,
    )
    db.add(event)
    db.commit()

    return {
        "asset": trigger.asset,
        "current_price": current_price,
        "condition": f"{trigger.condition} {trigger.target_value}",
        "fired": fired,
    }


# ==============================================================================
# ROLE OF THIS FILE:
# Holds the ONE real implementation of "check a trigger and act on it."
# Both the manual API endpoint and the automatic Celery task call this same
# function -- this is what stops the two code paths from silently drifting
# apart as the project grows.
# ==============================================================================