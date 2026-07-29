"""
schemas.py
----------
This file defines the "shape" of data going IN and OUT of our API.

Why do we need this if we already have models.py?
- models.py defines DATABASE tables (what's stored on disk).
- schemas.py defines API request/response shapes (what's sent over the internet).

They're often similar but not identical. For example, we NEVER want to send
a user's hashed_password back in an API response, even though it's a real
column in the database. Pydantic schemas let us control exactly what's exposed.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr


# ---------- User schemas ----------

class UserCreate(BaseModel):
    """What the client sends us when registering a new account."""
    email: EmailStr
    password: str


class UserOut(BaseModel):
    """What we send BACK to the client -- notice: no password field here."""
    id: int
    email: EmailStr
    telegram_chat_id: Optional[str] = None

    class Config:
        # Lets Pydantic read data straight from a SQLAlchemy model object,
        # instead of only from a plain dict.
        from_attributes = True


class UserLogin(BaseModel):
    """What the client sends us when logging in."""
    email: EmailStr
    password: str

class TelegramConnect(BaseModel):
    """What the client sends us to link their Telegram account."""
    chat_id: str
# ---------- Auth token schemas ----------

class Token(BaseModel):
    """What we send back after a successful login."""
    access_token: str
    token_type: str = "bearer"


# ---------- Trigger schemas ----------

class TriggerCreate(BaseModel):
    """What the client sends us when creating a new trigger."""
    asset: str            # e.g. "bitcoin"
    condition: str         # e.g. "<" or ">"
    target_value: float    # e.g. 50000.0


class TriggerOut(BaseModel):
    """What we send back when returning trigger information."""
    id: int
    asset: str
    condition: str
    target_value: float
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ==============================================================================
# ROLE OF THIS FILE:
# Defines what data the API accepts (request schemas) and what it returns
# (response schemas), separate from how data is stored in the database. This
# is what makes FastAPI validate incoming JSON automatically, and it's what
# keeps sensitive fields like hashed_password from ever leaking into a response.
# ==============================================================================
