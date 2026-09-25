import asyncio
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select

from config import settings
from connectors.registry import ConnectorRegistry
from database import SessionLocal
from models import Trigger
from notifications.registry import get_provider
from rules import evaluate

registry = ConnectorRegistry()

# Transient failures (network blips, upstream 5xx/timeouts) are worth
# retrying within a single check. Permanent failures (bad config, unknown
# field) are not — retrying them just burns time before the same error.
_RETRYABLE = (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError, httpx.HTTPStatusError)
_MAX_RETRIES = 3
_RETRY_DELAYS = [2, 8, 20]


def _format_message(trigger: Trigger, value: float) -> str:
    op_symbols = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "eq": "=="}
    condition = trigger.condition
    symbol = op_symbols.get(condition["operator"], condition["operator"])
    return (
        f"🔔 PingMe: \u00ab{trigger.name}\u00bb triggered!\n"
        f"{condition['field']} = {value} {symbol} {condition['value']}\n"
        f"(this alert has now been deactivated)"
    )


async def _check_once(trigger_id: int) -> None:
    """One fetch-evaluate cycle. Raises on failure so the caller can
    distinguish retryable vs permanent and apply backoff."""
    async with SessionLocal() as db:
        trigger = await db.get(Trigger, trigger_id)
        if trigger is None or not trigger.active:
            return

        connector = registry.get(trigger.source)  # ValueError -> permanent, not retried
        value = await connector.fetch(trigger.config)

        condition = trigger.condition
        matched = evaluate(value, condition["operator"], condition["value"])

        now = datetime.now(timezone.utc)
        trigger.last_checked_at = now
        trigger.last_value = value
        trigger.consecutive_failures = 0
        trigger.last_error = None

        if matched:
            provider = get_provider(trigger.notification["channel"])
            await provider.send(_format_message(trigger, value))
            trigger.triggered_at = now
            trigger.active = False  # one-shot: fire once, then stop
        else:
            trigger.next_check_at = now + timedelta(seconds=trigger.interval_seconds)

        await db.commit()


async def execute_trigger_once(trigger_id: int) -> None:
    last_exc: Exception | None = None

    for attempt in range(_MAX_RETRIES):
        try:
            await _check_once(trigger_id)
            return
        except _RETRYABLE as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES - 1:
                await asyncio.sleep(_RETRY_DELAYS[attempt])
        except (ValueError, KeyError) as exc:
            # Permanent — bad source name, missing field, etc. Don't retry.
            last_exc = exc
            break
        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES - 1:
                await asyncio.sleep(_RETRY_DELAYS[attempt])

    if last_exc is None:
        return

    async with SessionLocal() as db:
        trigger = await db.get(Trigger, trigger_id)
        if trigger is None:
            return
        now = datetime.now(timezone.utc)
        trigger.consecutive_failures += 1
        trigger.last_error = str(last_exc)[:500]
        trigger.last_checked_at = now

        if trigger.consecutive_failures >= settings.max_consecutive_failures:
            trigger.active = False
            trigger.last_error = (
                f"Deactivated after {trigger.consecutive_failures} consecutive failures: {trigger.last_error}"
            )
        else:
            trigger.next_check_at = now + timedelta(seconds=trigger.interval_seconds)

        await db.commit()
    print(f"[worker] trigger {trigger_id} check failed: {last_exc}")
