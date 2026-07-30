"""
internal_routes.py
--------------------
The production replacement for Celery Beat + Workers. Free hosts won't
run an always-on background process, so instead of a process that stays
awake and checks time itself, this exposes "check every trigger" as a
normal HTTP endpoint. Something else has to wake it up on a schedule --
that's what the GitHub Actions cron workflow does.

Secret-key protected because this endpoint checks every user's triggers
and sends Telegram messages -- it can't be public, or anyone could spam
CoinGecko/AQICN or spam users' phones.
"""

import os

from dotenv import load_dotenv
from fastapi import APIRouter, Header, HTTPException, status
from sqlalchemy.orm import Session
from fastapi import Depends

from app import models, trigger_service
from app.database import get_db

load_dotenv()

INTERNAL_CRON_SECRET = os.getenv("INTERNAL_CRON_SECRET")

router = APIRouter(prefix="/internal", tags=["internal"])


def verify_cron_secret(x_internal_secret: str = Header(...)):
    """
    FastAPI dependency: rejects the request before check_all() ever runs,
    unless the caller sent the correct secret in the X-Internal-Secret
    header. This is what stops this endpoint from being public.
    """
    if not INTERNAL_CRON_SECRET or x_internal_secret != INTERNAL_CRON_SECRET:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing internal secret")


@router.post("/check-all")
def check_all(db: Session = Depends(get_db), _=Depends(verify_cron_secret)):
    """
    Checks every active trigger, one at a time, synchronously.
    One trigger failing (bad coordinates, API down, etc.) is caught and
    recorded -- it does NOT stop the rest of the batch from being checked.
    """
    triggers = db.query(models.Trigger).filter(models.Trigger.is_active == True).all()

    checked = 0
    fired = 0
    errors = []

    for trigger in triggers:
        user = db.query(models.User).filter(models.User.id == trigger.user_id).first()
        if user is None or not user.telegram_chat_id:
            continue  # same skip rule tasks.py uses -- no Telegram, nowhere to alert

        try:
            result = trigger_service.run_trigger_check(trigger, user, db)
            checked += 1
            if result.get("fired"):
                fired += 1
        except Exception as e:
            errors.append({"trigger_id": trigger.id, "error": str(e)})

    return {"checked": checked, "fired": fired, "errors": errors}


# ==============================================================================
# ROLE OF THIS FILE:
# The free-hosting replacement for Celery Beat + Workers. Loops through
# every active trigger synchronously and reuses trigger_service, exactly
# like tasks.py does -- just triggered by an incoming HTTP request from
# GitHub Actions instead of Celery's own clock.
# ==============================================================================