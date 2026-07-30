# app/trigger_service.py
from sqlalchemy.orm import Session

from app import models
from app.trigger_handlers.registry import get_handler


def run_trigger_check(trigger: models.Trigger, user: models.User, db: Session) -> dict:
    handler = get_handler(trigger.trigger_type)
    return handler.check(trigger, user, db)