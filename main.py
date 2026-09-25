import asyncio
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from langchain_groq import ChatGroq
from pydantic import BaseModel
from sqlalchemy import select

from agent.planner import Planner
from config import settings
from connectors.registry import ConnectorRegistry
from database import SessionLocal, init_db
from models import DynamicConnectorConfig, Trigger
from scheduler import claim_due_triggers
from worker import execute_trigger_once

registry = ConnectorRegistry()

llm = ChatGroq(model=settings.model_name, api_key=settings.groq_api_key, temperature=0)
planner: Planner | None = None  # built in lifespan, after dynamic connectors are loaded

# In-memory session store — fine for a local demo (single process, no
# restart between requests). If this needs to survive a restart, move it
# to the DB; it doesn't need TTL logic added first, just persistence.
sessions: dict[str, dict] = {}


async def _load_dynamic_connectors():
    """
    Reload any connectors previously registered by the discovery agent
    (or manually) so they survive a restart without needing a code change.
    """
    async with SessionLocal() as db:
        result = await db.execute(select(DynamicConnectorConfig))
        rows = result.scalars().all()
    for row in rows:
        registry.register_dynamic(row.config)
    if rows:
        print(f"[startup] loaded {len(rows)} dynamic connector(s) from DB")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global planner
    await init_db()
    await _load_dynamic_connectors()
    # Built after dynamic connectors are loaded, so the intent classifier's
    # capability list includes anything the discovery agent registered
    # in a previous run.
    planner = Planner(llm=llm, registry=registry)
    # No in-process scheduler task anymore — Celery Beat + a Celery worker
    # (separate processes, see README) now handle periodic dispatch and
    # execution. This process is API-only.
    yield


app = FastAPI(title="PingMe", version="0.4.0", lifespan=lifespan)


class QueryRequest(BaseModel):
    query: str
    session_id: str | None = None


class TriggerPatch(BaseModel):
    active: bool | None = None


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/tick")
async def tick(secret: str | None = None):
    """
    Free-hosting path: no Celery/Redis in this deployment mode. An
    external cron (cron-job.org — same keepalive pattern already used for
    KeyShort on Neon) hits this endpoint periodically. It does exactly
    what Celery Beat + a worker would do — find due triggers, check them —
    just synchronously, in this one process, with no queue in between.
    The hit itself also keeps a free Render instance from spinning down.

    Locally, prefer the real Celery worker/beat (see README) — this path
    exists specifically because free PaaS tiers don't support an always-on
    background worker for $0, not because it's the better architecture.
    """
    if settings.tick_secret and secret != settings.tick_secret:
        raise HTTPException(status_code=403, detail="Invalid or missing secret")

    due_ids = await claim_due_triggers()
    if due_ids:
        await asyncio.gather(*[execute_trigger_once(tid) for tid in due_ids])

    return {"checked": len(due_ids), "trigger_ids": due_ids}


@app.post("/plan")
async def create_plan(request: QueryRequest):
    """
    Understands the request, asks for anything it's missing (multi-turn
    via session_id), fills parameters, resolves a check interval, verifies
    the plan against the live API, and — if everything checks out —
    persists it to the DB as an active Trigger. The scheduler picks it up
    on its own; nothing else needs to be called.
    """
    known_session = bool(request.session_id and request.session_id in sessions)
    pending = sessions.get(request.session_id, {}) if known_session else {}
    newly_confirmed_connector_config: dict | None = None

    if pending.get("type") == "proposal":
        # Previous turn proposed a connector found via discovery and is
        # waiting for confirmation. Any follow-up here is treated as
        # approval — register it for real (in-memory now; persisted to
        # the DB below only once it actually succeeds end to end) and
        # refresh the classifier so it can route to it this same request.
        newly_confirmed_connector_config = pending["proposal"]
        registry.register_dynamic(newly_confirmed_connector_config)
        planner.refresh_capabilities()
        print(f"[discovery] registered proposed connector "
              f"'{newly_confirmed_connector_config['name']}' after user confirmation")
        combined_query = pending["original_query"]
        sessions.pop(request.session_id, None)
        known_session = False  # fresh planning pass below, not a needs_input continuation
    elif known_session:
        combined_query = f"{pending['original_query']}\nAdditional detail from user: {request.query}"
    else:
        combined_query = request.query

    try:
        result = await planner.plan(combined_query)
    except Exception as exc:
        return {"status": "error", "message": f"Something went wrong while planning: {exc}"}

    session_id = request.session_id or str(uuid.uuid4())

    if result["status"] == "needs_input":
        current_missing = set(result.get("missing", []))
        previous_missing = set(sessions.get(session_id, {}).get("missing", []))

        if known_session and current_missing and current_missing == previous_missing:
            # Same fields still unresolved after a follow-up — say so
            # explicitly instead of repeating an identical message, which
            # looks like nothing happened at all.
            result["message"] = (
                f"Still couldn't resolve: {', '.join(current_missing)}. "
                f"Try a different or more specific input (e.g. a well-known "
                f"nearby city instead of a landmark name)."
            )

        sessions[session_id] = {"original_query": combined_query, "missing": list(current_missing)}
        result["session_id"] = session_id
        return result

    if result["status"] == "proposed_connector":
        # Found nothing built-in, but discovery proposed a source from
        # the web. Hold it for confirmation rather than registering
        # anything the user hasn't reviewed. See discovery.py — this
        # status only ever appears if settings.enable_discovery is on.
        sessions[session_id] = {
            "type": "proposal",
            "original_query": combined_query,
            "proposal": result["proposal"],
        }
        result["session_id"] = session_id
        return result

    if known_session:
        sessions.pop(request.session_id, None)

    if result["status"] != "ready":
        if newly_confirmed_connector_config:
            # Registered in-memory for this attempt but never made it to
            # "ready" — don't leave a broken/unverified connector sitting
            # in the live registry for future requests to stumble into.
            registry.connectors.pop(newly_confirmed_connector_config["name"], None)
            planner.refresh_capabilities()
        return result  # unsupported / infeasible

    plan = result["plan"]
    if plan["condition"] is None:
        # No threshold was ever stated — this was a one-off "what's the
        # value right now" question, not something to schedule.
        return {
            "status": "answered",
            "message": (
                f"Current {plan['source']} value: {plan['verified_value']}. "
                f"No threshold was specified, so nothing was scheduled — "
                f"say something like 'notify me when it drops below X' to create an alert."
            ),
            "plan": plan,
        }

    trigger = Trigger(
        name=combined_query[:200],
        source=plan["source"],
        config=plan["config"],
        condition=plan["condition"],
        notification={"channel": "telegram"},
        interval_seconds=plan["interval_seconds"],
    )
    async with SessionLocal() as db:
        if newly_confirmed_connector_config:
            # Verified end to end now — persist it so it's part of the
            # registry for future requests too, not just this one.
            db.add(DynamicConnectorConfig(
                name=newly_confirmed_connector_config["name"],
                config=newly_confirmed_connector_config,
            ))
        db.add(trigger)
        await db.commit()
        await db.refresh(trigger)

    return {
        "status": "scheduled",
        "trigger_id": trigger.id,
        "message": (
            f"Watching {plan['source']} — will check every {plan['interval_seconds']}s "
            f"({plan['interval_reason']}). Current value: {plan['verified_value']}. "
            f"Will notify once and then stop when "
            f"{plan['condition']['field']} {plan['condition']['operator']} {plan['condition']['value']}."
        ),
        "plan": plan,
    }


@app.get("/triggers")
async def list_triggers():
    async with SessionLocal() as db:
        result = await db.execute(select(Trigger).order_by(Trigger.created_at.desc()))
        triggers = result.scalars().all()
    return [
        {
            "id": t.id,
            "name": t.name,
            "source": t.source,
            "config": t.config,
            "condition": t.condition,
            "interval_seconds": t.interval_seconds,
            "active": t.active,
            "last_value": t.last_value,
            "last_checked_at": t.last_checked_at,
            "next_check_at": t.next_check_at,
            "triggered_at": t.triggered_at,
            "consecutive_failures": t.consecutive_failures,
            "last_error": t.last_error,
        }
        for t in triggers
    ]


@app.patch("/triggers/{trigger_id}")
async def patch_trigger(trigger_id: int, patch: TriggerPatch):
    async with SessionLocal() as db:
        trigger = await db.get(Trigger, trigger_id)
        if trigger is None:
            raise HTTPException(status_code=404, detail="Trigger not found")
        if patch.active is not None:
            trigger.active = patch.active
        await db.commit()
        await db.refresh(trigger)
    return {"id": trigger.id, "active": trigger.active}


@app.post("/triggers/{trigger_id}/check-now")
async def check_trigger_now(trigger_id: int):
    """
    Forces one check immediately, bypassing next_check_at — for verifying
    the fetch/evaluate/notify path works without waiting on the scheduler's
    poll interval. Does NOT prove the automatic scheduler loop itself is
    alive; watch the server console for `[scheduler] N trigger(s) due`
    lines for that.
    """
    async with SessionLocal() as db:
        trigger = await db.get(Trigger, trigger_id)
        if trigger is None:
            raise HTTPException(status_code=404, detail="Trigger not found")
        before = {
            "active": trigger.active,
            "last_checked_at": trigger.last_checked_at,
            "last_value": trigger.last_value,
        }

    await execute_trigger_once(trigger_id)

    async with SessionLocal() as db:
        trigger = await db.get(Trigger, trigger_id)
        if trigger is None:
            return {"before": before, "after": None}
        after = {
            "active": trigger.active,
            "last_checked_at": trigger.last_checked_at,
            "last_value": trigger.last_value,
            "triggered_at": trigger.triggered_at,
            "last_error": trigger.last_error,
        }

    return {"before": before, "after": after}


@app.delete("/triggers/{trigger_id}")
async def delete_trigger(trigger_id: int):
    async with SessionLocal() as db:
        trigger = await db.get(Trigger, trigger_id)
        if trigger is None:
            raise HTTPException(status_code=404, detail="Trigger not found")
        await db.delete(trigger)
        await db.commit()
    return {"status": "deleted", "id": trigger_id}
