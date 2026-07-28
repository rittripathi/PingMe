"""
routers/auth_routes.py
-----------------------
API endpoints for registering a new account and logging in.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import auth, models, schemas
from app.database import get_db

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=schemas.UserOut)
def register(user_in: schemas.UserCreate, db: Session = Depends(get_db)):
    """
    Create a new user account.
    Steps:
      1. Check the email isn't already taken.
      2. Hash the password (never store it in plain text!).
      3. Save the new user row.
    """
    existing_user = db.query(models.User).filter(models.User.email == user_in.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email is already registered")

    new_user = models.User(
        email=user_in.email,
        hashed_password=auth.hash_password(user_in.password),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)  # reloads new_user with the id the database assigned

    return new_user


@router.post("/login", response_model=schemas.Token)
def login(credentials: schemas.UserLogin, db: Session = Depends(get_db)):
    """
    Check email + password. If correct, hand back a JWT access token.
    The client attaches this token to every future request as:
        Authorization: Bearer <token>
    """
    user = db.query(models.User).filter(models.User.email == credentials.email).first()

    if user is None or not auth.verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    access_token = auth.create_access_token(data={"sub": str(user.id)})
    return {"access_token": access_token, "token_type": "bearer"}


# ==============================================================================
# ROLE OF THIS FILE:
# Exposes /auth/register and /auth/login as HTTP endpoints. This is the ONLY
# file that creates users or hands out tokens -- every other protected route
# just checks whether a valid token was given (see auth.py's get_current_user).
# ==============================================================================
