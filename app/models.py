"""
models.py
---------
This file defines our database tables as Python classes.
Each class = one table. Each attribute = one column.
SQLAlchemy translates these classes into real SQL tables for us.
"""

from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class User(Base):
    """
    A person who has signed up for PingMe.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    # We'll fill this in when the user connects their Telegram account.
    # It's how we know WHERE to send their alerts. Not used yet in Phase 1.
    telegram_chat_id = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # This creates a link in Python: user.triggers gives you every trigger
    # this user owns, without writing a manual SQL join.
    triggers = relationship("Trigger", back_populates="owner", cascade="all, delete")


class Trigger(Base):
    """
    One alert rule the user created, e.g.
    "ping me when bitcoin price drops below $50,000".

    Important Phase 1 note: this table only STORES the rule. Nothing checks
    it against a real price yet -- that logic gets added in a later phase.
    """
    __tablename__ = "triggers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # What kind of thing are we watching? For now we only support "PRICE",
    # but this column is designed so we can add more types later
    # (e.g. "PNR_STATUS", "AQI") without changing the database structure.
    trigger_type = Column(String, nullable=False, default="PRICE")

    # Which asset? e.g. "bitcoin", "ethereum"
    asset = Column(String, nullable=False)

    # The comparison to check, e.g. "<" or ">"
    condition = Column(String, nullable=False)

    # The number to compare against, e.g. 50000.0
    target_value = Column(Float, nullable=False)

    # Is this trigger currently active, or has the user paused it?
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Link back to the user who owns this trigger.
    owner = relationship("User", back_populates="triggers")

    # Link to this trigger's history of checks (used starting Phase 3).
    events = relationship("TriggerEvent", back_populates="trigger", cascade="all, delete")


class TriggerEvent(Base):
    """
    A log entry for every time we check a trigger's condition.

    This table stays empty in Phase 1 -- we're creating the structure now so
    it's ready the moment the scheduler (Phase 3) starts writing to it.
    Storing every check (not just the ones that fire) is what lets us later
    answer "why didn't my alert fire?" -- a real observability feature.
    """
    __tablename__ = "trigger_events"

    id = Column(Integer, primary_key=True, index=True)
    trigger_id = Column(Integer, ForeignKey("triggers.id"), nullable=False)

    checked_value = Column(Float, nullable=True)
    fired = Column(Boolean, default=False)

    checked_at = Column(DateTime(timezone=True), server_default=func.now())

    trigger = relationship("Trigger", back_populates="events")


# ==============================================================================
# ROLE OF THIS FILE:
# Defines the shape of our data -- Users, Triggers, and TriggerEvents -- as
# Python classes that SQLAlchemy turns into real Postgres tables. This is the
# "nouns" of the app. The "verbs" (creating, checking, notifying) live in the
# router and (later) worker files, not here.
# ==============================================================================
