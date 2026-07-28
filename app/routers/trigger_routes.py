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

from app import auth, models, schemas
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


# ==============================================================================
# ROLE OF THIS FILE:
# Exposes /triggers endpoints (create, list, delete), all protected by login.
# This is where a user's "ping me when..." rules get stored. In later phases,
# a background worker reads from this same `triggers` table to decide what
# to check -- this file never talks to CoinGecko or Telegram directly.
# ==============================================================================
