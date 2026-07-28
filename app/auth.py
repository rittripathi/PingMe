"""
auth.py
-------
This file handles everything related to passwords and login tokens (JWT):
- turning a plain password into a secure hash (and checking it back)
- creating a JWT "access token" when someone logs in
- reading that token on later requests to figure out who's making the request
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import  HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app import models
from app.database import get_db

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

if SECRET_KEY is None:
    raise ValueError("SECRET_KEY is not set. Check your .env file.")

# passlib handles hashing passwords with bcrypt, so we NEVER store plain
# text passwords in the database.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# This tells FastAPI: "expect a Bearer token in the Authorization header,
# and here's the URL where a client would normally go to GET one"
# (mainly used to power the "Authorize" button in the /docs page).
bearer_scheme = HTTPBearer()

def hash_password(password: str) -> str:
    """Turn a plain-text password into a secure hash before saving it."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check a plain-text password against the stored hash at login time."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict) -> str:
    """
    Create a signed JWT containing 'data' (in our case, the user's id).
    The signature (created using SECRET_KEY) is what stops anyone from
    forging a token -- they'd need our secret key to create a valid one.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> models.User:

    """
    This is a FastAPI dependency used on every PROTECTED endpoint.
    It reads the Bearer token from the request, decodes it, and looks up
    the matching user in the database. If anything is wrong (missing token,
    expired token, tampered token, user no longer exists), it rejects the
    request with a 401 error before your endpoint code ever runs.
    """
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: Optional[str] = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    if user is None:
        raise credentials_exception

    return user


# ==============================================================================
# ROLE OF THIS FILE:
# Handles password hashing and JWT creation/verification. This is what makes
# "protected" endpoints possible -- any route that adds
# `current_user: models.User = Depends(get_current_user)` automatically
# requires a valid login token and gets access to who's making the request.
# ==============================================================================
