# PingMe — unified local build

Understands a request, asks for anything it's missing, fills parameters,
decides how often to check, proves the plan works against the live API,
schedules it, and fires it exactly once. Execution runs on **Celery +
Redis** — a dispatcher (Celery Beat) polls for due triggers on a fixed
tick and enqueues them; isolated worker processes pull from the queue
and do the actual fetch/evaluate/notify, independently retryable and
scalable from the dispatch tick itself.

## Run it

Four things run: Redis, the FastAPI app, a Celery worker, and Celery
Beat. Four terminals (or a process manager) — this is genuinely a
multi-process system now, not a single-command demo.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # put your Groq API key in .env
```

**Terminal 1 — Redis** (skip if you already have one running):
```bash
redis-server
```
For deployment, Upstash's free Redis tier works — just put its
`rediss://` URL in `REDIS_URL` in `.env`; nothing else changes.

**Terminal 2 — the API:**
```bash
uvicorn main:app --reload
```

**Terminal 3 — a Celery worker** (does the actual fetch/evaluate/notify):
```bash
celery -A celery_app worker --loglevel=info
```

**Terminal 4 — Celery Beat** (finds due triggers, enqueues them on a
fixed tick — `SCHEDULER_POLL_SECONDS` in `.env`, default 5s):
```bash
celery -A celery_app beat --loglevel=info
```

Telegram is optional: leave `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` blank
and notifications print to the worker's console instead of failing.

## Try it

```bash
curl -X POST localhost:8000/plan \
  -H "Content-Type: application/json" \
  -d '{"query": "notify me when bitcoin drops below 90000 usd, check every 2 minutes"}'
```

Watch **the worker's terminal**, not the API's — that's where
fetch/evaluate/notify actually happens now. `GET /triggers` still works
the same as before for checking state.

```bash
curl localhost:8000/triggers
```

If a request is missing something, the response includes a `session_id`
— send it back with the missing detail and the planner combines it with
your original request instead of starting over:

```bash
curl -X POST localhost:8000/plan \
  -H "Content-Type: application/json" \
  -d '{"query": "Delhi", "session_id": "<id from previous response>"}'
```

## Celery + Redis — what was actually verified

Unlike the discovery agent (openly flagged as unverified further down),
this was tested against a real, running Redis instance and real Celery
worker/beat processes, not just unit-tested in isolation. That testing
caught and fixed two real bugs:

- **A retry-limit off-by-one** in the self-correction loop (planner.py) —
  gave up after 2 attempts instead of the intended 3.
- **A dispatch race** introduced specifically by moving to a decoupled
  queue: Beat's tick doesn't wait for a previous check to finish, so a
  check slower than one tick (e.g. mid-retry against a flaky API) got
  dispatched a second time before the first completed. Confirmed via a
  live run: a trigger whose check took longer than the 5s Beat interval
  was dispatched twice. Fixed by having `claim_due_triggers`
  provisionally push `next_check_at` forward *at claim time*, in the
  same transaction as the select, not just when the check completes —
  closes the race window instead of relying on timing luck.

Verified live end-to-end: Redis connectivity, a real Celery worker
receiving and executing a dispatched task, the worker actually reaching
a real external API (CoinGecko — got a live 403, likely the sandbox's
egress IP being blocked, not a config issue) through 3 retries with the
correct backoff timing, and the failure being correctly persisted to
the trigger row. Also verified Beat firing its schedule automatically
and — after the fix above — dispatching each due trigger exactly once.

## Hosting for free

The Celery/Redis setup above is the real architecture and what's
verified — keep using it locally, and for walking through the code. For
$0 hosting, it doesn't fit: free PaaS tiers are built around "sleep when
idle," and an always-on Celery worker fundamentally isn't. So the free
path is a deliberate downgrade, not a hidden compromise:

**One Render free web service. No worker, no Beat, no Redis.**
`POST /tick` (in `main.py`) does exactly what Celery Beat + a worker
would do — find due triggers, check them — just synchronously, in this
one process, no queue in between. It reuses the *same* `claim_due_triggers`
and `execute_trigger_once` functions the Celery path uses, so it's not a
separate, unverified code path — verified directly above with a live
test (inserted a due trigger, called `tick()`, confirmed it actually
processed and updated the row).

**Setup:**
1. **Neon** — free Postgres. Render's free web service has an ephemeral
   filesystem (wiped on restart/redeploy), so SQLite won't persist data —
   swap `DATABASE_URL` to Neon's `postgresql+asyncpg://...` connection
   string. `asyncpg` is already in `requirements.txt`; nothing else in
   `database.py`/`models.py` needs to change.
2. **Render** — deploy `render.yaml` (already in this repo) as a
   Blueprint, or manually: free web service, build
   `pip install -r requirements.txt`, start
   `uvicorn main:app --host 0.0.0.0 --port $PORT`. Set `GROQ_API_KEY`,
   `DATABASE_URL` (from step 1), and **`TICK_SECRET`** — pick a random
   string. Without it, `/tick` is a public endpoint anyone can hit to
   trigger real external API calls and DB writes on your behalf.
3. **cron-job.org** — same pattern as KeyShort's Neon keepalive. Point it
   at `https://your-app.onrender.com/tick?secret=<your TICK_SECRET>`,
   every 1 minute (matches the fastest connector floor —
   `min_interval_seconds=60` on most connectors). Each hit both checks
   due triggers and keeps the free instance from spinning down.

**What you lose vs. the Celery path, honestly:** no worker isolation (one
slow check blocks the next tick's other checks, since it's all
sequential in one process now), no independent retry-queue durability if
the process restarts mid-check, and check timing is only as reliable as
cron-job.org's own schedule rather than a dedicated Beat process. For a
portfolio project's actual running instance, that's a reasonable trade
for $0; it's worth being able to explain plainly if asked, rather than
implying the hosted instance runs the full distributed version.

## What changed from the two separate Phase 1 / Phase 2 projects

**One connector interface instead of two.** `apis/*.py` (planning) and
`app/connectors/*.py` (execution) were duplicating the same CoinGecko/
weather logic with different shapes. `connectors/base.py` now has a
single `Connector` class — the planner uses its `capabilities` /
`parameters` / `value_field` to match intent and validate params; the
scheduler uses its `fetch()` to get a live value. Same object, same file,
no drift between what the agent thinks a connector does and what it
actually does.

**One-shot alerts, not continuous monitors.** Earlier drafts kept
checking forever and re-armed after a condition went false and became
true again. That's not what "ping me when X happens" means — once it
happens, you don't need more pings. A `Trigger` now fires once and sets
`active = False`. No hysteresis/cooldown logic needed — deactivating
*is* the cooldown.

**A dedicated interval-resolution step.** `agent/interval_resolver.py`
is its own tool, separate from parameter filling: it takes an explicit
frequency if the user stated one ("check every 5 minutes"), clamps it to
the connector's `min_interval_seconds` floor, and otherwise falls back to
the connector's own `default_interval_seconds` — its judgment about how
fast that particular data source changes. Deterministic, not an LLM
call — the inputs are already concrete numbers.

**Verification before scheduling.** Before anything is written to the
DB, the planner calls `connector.fetch()` for real. A wrong `coin_id` or
bad coordinates fails here, loudly, with the actual HTTP error — not
silently as a trigger that will never fire.

**Auto-persist on `ready`.** `/plan` returns `"scheduled"` with the
trigger's id, not just a plan the caller has to remember to submit
somewhere else. The scheduler picks it up on its own next tick — there's
no second step.

## Scheduling logic

```text
due  ⟺  trigger.active AND trigger.next_check_at <= now()
```

`next_check_at` is set to `now + interval_seconds` at claim time (Beat's
dispatch), and again to the same formula on a non-matching check
completion — the claim-time write closes the double-dispatch race
described above; the completion-time write is the accurate value for
normal operation. Each trigger carries its own interval, so a 2-minute
crypto watch and a 30-minute AQI watch are both served correctly by the
same 5-second Beat tick — it just does far less work per tick for the
slow one.

On match: notify once, set `triggered_at`, set `active = False`. Done.

On failure: retry transient errors (timeouts, connection issues) up to 3
times with backoff within one check; permanent errors (bad config, an
unknown field) fail immediately without wasting retries. After
`MAX_CONSECUTIVE_FAILURES` checks in a row fail, the trigger deactivates
itself with the error recorded — it won't retry forever silently.

## Adding a new connector

Two ways now:

1. **Hand-written** — subclass `Connector` in `connectors/`, register in
   `connectors/registry.py`. Still the right choice for anything needing
   real logic (custom auth, POST bodies, pagination).
2. **Config-driven (`DynamicConnector`)** — for the common case (GET a
   JSON endpoint, read one number out of it), no Python file needed at
   all. `registry.register_dynamic(config)` takes a plain dict — base
   URL, params, and a JMESPath to the value — and it behaves exactly
   like any other connector from then on. This is what makes "thousands
   of public APIs" tractable: the code is written once, the rest is data.

## Agentic upgrades in this version

**Self-correction loop.** Previously, a failed live verification
(`verify_request`) just killed the plan. Now `planner.py` routes a
failure back into `fill_parameters` with the error attached as context,
up to `MAX_VERIFY_RETRIES` times, before giving up — the agent gets a
chance to try again informed by what actually went wrong, instead of
one blind guess. Verified with a fake flaky connector (fails twice,
succeeds on the 3rd try → plan succeeds) and a permanently-failing one
(gives up after exactly `MAX_VERIFY_RETRIES + 1` attempts) — see the
test commands in the build history.

**Disambiguation instead of blind guessing.** `geocode_location` now
returns up to 5 candidates instead of silently picking the top one.
`ParameterResolution` gained a `suggestions` field — when a tool result
is genuinely ambiguous ("Paris" → France or Texas), the response asks
which one instead of guessing, with the candidates included so the next
message can just be "the first one" or "Paris, France."

**Discovery agent (`agent/discovery.py`) — off by default.** Searches
[apis.guru](https://apis.guru)'s free, keyless index of ~2000+ public
APIs by keyword, has the LLM read the actual OpenAPI spec of the best
match, and proposes a `DynamicConnector` config. The proposal goes
through the same `session_id` confirmation flow as a missing-parameter
question — nothing is registered until you approve it, and nothing is
*persisted* to the DB until it's actually verified end-to-end (a
rejected or failed proposal is torn back out of the in-memory registry).

**Honesty about what's tested here:** the keyword-ranking logic in
`discovery.py` is unit-tested offline against a mocked apis.guru index
and works correctly. The live parts — fetching the real apis.guru
index, fetching a real OpenAPI spec, and having the LLM read it — are
**not verified**, because this was built in a sandbox with no network
access to apis.guru or a live LLM. Set `ENABLE_DISCOVERY=true` in
`.env` to try it, and expect to debug the spec-truncation and prompt
against real spec shapes, which vary a lot in size and structure.

## Known local-demo simplifications (flagged, not hidden)

- SQLite: fine for a single Celery worker; if you scale to multiple
  worker processes hitting the DB concurrently, this is the point to
  move to Postgres (Neon's free tier is a one-line `DATABASE_URL`
  change — nothing else in `database.py` or `models.py` needs to change).
- Run exactly one Celery Beat instance. Beat's job is "find due triggers,
  enqueue them" — running two Beats would double-dispatch, since neither
  knows about the other's claim. Celery workers, in contrast, scale fine
  to as many as you want; they just pull from the same queue.
- No human-confirmation step before persisting a `"ready"` plan — the
  earlier design discussed always asking "create this?" first; this
  version auto-schedules. Easy to reintroduce: hold the plan in
  `sessions` and require a second `/plan` call with e.g. `"confirm"`
  before the `Trigger` insert happens.
- In-memory session store — resets on restart. Fine for a local demo;
  move to the DB if that matters later.
