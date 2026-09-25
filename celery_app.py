from celery import Celery

from config import settings

celery_app = Celery(
    "pingme",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Celery Beat replaces the old in-process asyncio scheduler loop —
    # this tick just finds due triggers and enqueues one task per trigger;
    # the actual fetch/evaluate/notify work happens in worker processes,
    # decoupled from this dispatch tick and retryable independently.
    beat_schedule={
        "dispatch-due-triggers": {
            "task": "tasks.dispatch_due_triggers",
            "schedule": settings.scheduler_poll_seconds,
        },
    },
)

# Imported here (not autodiscover_tasks, since this is a flat module, not
# a package) so `celery -A celery_app worker` and `celery -A celery_app
# beat` both see the task definitions. tasks.py imports celery_app back —
# safe because celery_app is fully defined above this line before tasks.py
# runs its own `from celery_app import celery_app`.
import tasks  # noqa: E402,F401
