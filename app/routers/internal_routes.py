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

    if not INTERNAL_CRON_SECRET or x_internal_secret != INTERNAL_CRON_SECRET:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing internal secret")


@router.post("/check-all")
def check_all(db: Session = Depends(get_db), _=Depends(verify_cron_secret)):
    triggers = db.query(models.Trigger).filter(models.Trigger.is_active == True).all()

    checked = 0
    fired = 0
    errors = []

    for trigger in triggers:
        user = db.query(models.User).filter(models.User.id == trigger.user_id).first()
        if user is None or not user.telegram_chat_id:
            continue  
        try:
            result = trigger_service.run_trigger_check(trigger, user, db)
            checked += 1
            if result.get("fired"):
                fired += 1
        except Exception as e:
            errors.append({"trigger_id": trigger.id, "error": str(e)})

    return {"checked": checked, "fired": fired, "errors": errors}

