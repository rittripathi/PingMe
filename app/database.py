"""
database.py
------------
This file sets up the connection between our FastAPI app and the PostgreSQL
database.

Think of this file as the "wiring" that lets the rest of the app talk to the
database without every other file needing to know the connection details.
"""

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Load variables from the .env file (like DATABASE_URL) into the environment.
load_dotenv()

# Read the database connection string from environment variables.
# Example: postgresql://pingme:pingme@localhost:5432/pingme_db
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL is None:
    raise ValueError(
        "DATABASE_URL is not set. Did you copy .env.example to .env and fill it in?"
    )

# The "engine" is SQLAlchemy's core connection to the database.
engine = create_engine(DATABASE_URL)

# SessionLocal is a factory that creates new database "sessions".
# A session is like a temporary workspace where you read/write data,
# then either save (commit) or discard (rollback) your changes.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base is the parent class that all our database models (tables) will
# inherit from. SQLAlchemy uses this to know which Python classes map to
# which database tables.
Base = declarative_base()


def get_db():
    """
    This is a FastAPI "dependency". Any endpoint that needs database access
    calls this function to get a session, uses it, and the session is
    automatically closed afterwards -- even if an error happens along the way.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ==============================================================================
# ROLE OF THIS FILE:
# Sets up the database connection (engine + session factory) that every other
# file uses to talk to Postgres. Nothing in this file is PingMe-specific --
# it's boilerplate you'd write for almost any FastAPI + SQLAlchemy project.
# ==============================================================================
