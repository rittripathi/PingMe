import asyncio

from celery_app import celery_app
from scheduler import claim_due_triggers
import worker as worker_module


@celery_app.task(name="tasks.check_trigger_task")
def check_trigger_task(trigger_id: int):
    """
    Celery task wrapper around the async fetch/evaluate/notify logic in
    worker.py. Celery tasks are synchronous by contract — this is the
    boundary where the existing async worker code meets Celery's
    execution model. Each invocation gets its own event loop.
    """
    asyncio.run(worker_module.execute_trigger_once(trigger_id))


@celery_app.task(name="tasks.dispatch_due_triggers")
def dispatch_due_triggers():
    """
    Runs on Celery Beat's schedule (see celery_app.py). Finds due triggers
    and enqueues one check_trigger_task per trigger onto the Celery
    queue — replaces the old in-process asyncio scheduler loop entirely.
    Same due-query as before: active AND next_check_at <= now. The actual
    work now happens in isolated worker processes, retryable and scalable
    independently of this dispatch tick.
    """
    due_ids = asyncio.run(claim_due_triggers())
    for trigger_id in due_ids:
        check_trigger_task.delay(trigger_id)
    if due_ids:
        print(f"[celery-beat] dispatched {len(due_ids)} trigger(s): {due_ids}")
    
