"""
main.py
-------
This is the entry point of our FastAPI application.
Run it with:  uvicorn app.main:app --reload
"""

from fastapi import FastAPI
from app.routers import auth_routes, trigger_routes, user_routes, internal_routes
from app.database import Base, engine

# This line looks at every model defined in models.py (via Base) and creates
# the matching tables in Postgres if they don't already exist.
# NOTE: this is fine for Phase 1 learning. In a real production app, you'd
# use a migration tool (Alembic) instead so you can change tables safely
# without losing data -- that's something we can add in a later phase.
Base.metadata.create_all(bind=engine)
app = FastAPI(
    title="PingMe",
    description="A unified alert platform -- ping me when X happens.",
    version="0.1.0",
)

# Plug in our route files. Each one owns a URL prefix (/auth, /triggers).

app.include_router(auth_routes.router)
app.include_router(user_routes.router)
app.include_router(trigger_routes.router)
app.include_router(internal_routes.router)


@app.get("/health")
def health_check():
    """Simple endpoint to confirm the server is up and responding."""
    return {"status": "ok"}


# ==============================================================================
# ROLE OF THIS FILE:
# Creates the FastAPI app, creates database tables on startup, and wires in
# the route files (auth_routes, trigger_routes). This is the file you point
# uvicorn at to actually run the server.
# ==============================================================================
