"""
routers/trigger_routes.py
---------------------------
API endpoints for creating, listing, and deleting triggers.

Important Phase 1 note: creating a trigger here only SAVES it to the
database. Nothing actually checks the bitcoin price or sends a Telegram
message yet -- that logic gets added in Phase 2 and Phase 3.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import auth, models, schemas,notifier, price_service, trigger_service
from app.database import get_db

router = APIRouter(prefix="/triggers", tags=["Triggers"])


@router.post("/", response_model=schemas.TriggerOut)
def create_trigger(
    trigger_in: schemas.TriggerCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Create a new trigger for the logged-in user.
    `current_user` is filled in automatically by the get_current_user
    dependency -- it reads the JWT from the request and looks up the user,
    so this function never has to handle login logic itself.
    """
    new_trigger = models.Trigger(
        user_id=current_user.id,
        asset=trigger_in.asset,
        condition=trigger_in.condition,
        target_value=trigger_in.target_value,
    )
    db.add(new_trigger)
    db.commit()
    db.refresh(new_trigger)
    return new_trigger


@router.get("/", response_model=List[schemas.TriggerOut])
def list_triggers(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Return only the triggers that belong to the logged-in user."""
    return db.query(models.Trigger).filter(models.Trigger.user_id == current_user.id).all()


@router.delete("/{trigger_id}")
def delete_trigger(
    trigger_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Delete a trigger -- but ONLY if it belongs to the logged-in user.
    This ownership check matters: without it, any logged-in user could
    delete anyone else's trigger just by guessing an ID number.
    """
    trigger = (
        db.query(models.Trigger)
        .filter(models.Trigger.id == trigger_id, models.Trigger.user_id == current_user.id)
        .first()
    )
    if trigger is None:
        raise HTTPException(status_code=404, detail="Trigger not found")

    db.delete(trigger)
    db.commit()
    return {"detail": f"Trigger {trigger_id} deleted"}

@router.post("/{trigger_id}/check")
def check_trigger_now(
    trigger_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Manually run ONE trigger's check right now, instead of waiting for the
    scheduler. Delegates the actual price-check-notify-log work to
    trigger_service.run_trigger_check -- the exact same function the
    automatic Celery task (Phase 3) calls every 60 seconds.
    """
    trigger = (
        db.query(models.Trigger)
        .filter(models.Trigger.id == trigger_id, models.Trigger.user_id == current_user.id)
        .first()
    )
    if trigger is None:
        raise HTTPException(status_code=404, detail="Trigger not found")

    if not current_user.telegram_chat_id:
        raise HTTPException(
            status_code=400,
            detail="Connect your Telegram first via POST /users/me/telegram",
        )

    try:
        return trigger_service.run_trigger_check(trigger, current_user, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    fired = price_service.condition_met(current_price, trigger.condition, trigger.target_value)

    if fired:
        message = (
            f"PingMe alert: {trigger.asset} is now {current_price} "
            f"(condition: {trigger.condition} {trigger.target_value})"
        )
        notifier.send_telegram_message(current_user.telegram_chat_id, message)

    # Log this check either way -- fired or not -- so we build a real history.
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
# Exposes /triggers endpoints (create, list, delete), all protected by login.
# This is where a user's "ping me when..." rules get stored. In later phases,
# a background worker reads from this same `triggers` table to decide what
# to check -- this file never talks to CoinGecko or Telegram directly.
# ==============================================================================
