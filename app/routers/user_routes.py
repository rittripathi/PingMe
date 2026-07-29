"""
routers/user_routes.py
------------------------
Endpoints for managing your own account details -- right now just
connecting your Telegram chat ID so PingMe knows where to send your alerts.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import auth, models, schemas
from app.database import get_db

router = APIRouter(prefix="/users", tags=["Users"])


@router.post("/me/telegram", response_model=schemas.UserOut)
def connect_telegram(
    payload: schemas.TelegramConnect,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Save the logged-in user's Telegram chat ID onto their account.
    Run this once after getting your chat ID from @BotFather / getUpdates --
    from then on, PingMe knows where to send YOUR alerts specifically.
    """
    current_user.telegram_chat_id = payload.chat_id
    db.commit()
    db.refresh(current_user)
    return current_user


# ==============================================================================
# ROLE OF THIS FILE:
# Exposes /users/me/telegram so a logged-in user can link their own Telegram
# chat ID to their account. This is what finally connects the "who you are"
# (JWT/user_id) side of the app to the "where to message you" (Telegram) side.
# ==============================================================================