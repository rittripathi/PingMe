import os

from celery import Celery
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "pingme",
    broker=REDIS_URL,   
    backend=REDIS_URL,  
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