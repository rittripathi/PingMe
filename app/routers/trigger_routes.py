from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import auth, models, schemas, trigger_service
from app.database import get_db

router = APIRouter(prefix="/triggers", tags=["Triggers"])


@router.post("/", response_model=schemas.TriggerOut)
def create_trigger(
    trigger_in: schemas.TriggerCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    new_trigger = models.Trigger(
        user_id=current_user.id,
        asset=trigger_in.asset,
        trigger_type=trigger_in.trigger_type,
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
    return db.query(models.Trigger).filter(models.Trigger.user_id == current_user.id).all()


@router.delete("/{trigger_id}")
def delete_trigger(
    trigger_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
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
    