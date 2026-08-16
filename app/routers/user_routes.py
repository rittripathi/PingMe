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
    current_user.telegram_chat_id = payload.chat_id
    db.commit()
    db.refresh(current_user)
    return current_user

