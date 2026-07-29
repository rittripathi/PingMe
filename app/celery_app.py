"""
celery_app.py
--------------
Sets up Celery -- the background task system PingMe uses to run trigger
checks automatically, on a schedule, instead of only when someone manually
calls POST /triggers/{id}/check.

Two moving pieces work together:
  - Celery BEAT is a scheduler. It doesn't check any prices itself -- every
    interval, it just says "time to run this task" and drops a job in Redis.
  - Celery WORKERS pick jobs up from Redis and actually run them.

These run as two separate terminal processes (see below) -- neither one is
uvicorn, and uvicorn doesn't need to know they exist.
"""

import os

from celery import Celery
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "pingme",
    broker=REDIS_URL,   # where beat drops jobs, and workers pick them up from
    backend=REDIS_URL,  # where task results get stored
)

# Tells Celery to look inside app/tasks.py for @celery_app.task functions.
celery_app.autodiscover_tasks(["app"])

# Celery beat's schedule: run "check-all-triggers-every-minute" once every
# 60 seconds, calling the task defined in app/tasks.py.
celery_app.conf.beat_schedule = {
    "check-all-triggers-every-minute": {
        "task": "app.tasks.check_all_triggers",
        "schedule": 60.0,  # seconds
    },
}
celery_app.conf.timezone = "UTC"


# ==============================================================================
# ROLE OF THIS FILE:
# Configures Celery itself -- how it connects to Redis, and what schedule
# Celery beat should follow. No trigger-checking logic lives here; that's
# in tasks.py. Think of this file as Celery's settings file.
# ==============================================================================