# PingMe — Agentic Condition-Based Alerting Platform

**PingMe** is an agentic alerting platform that converts natural-language requests into verified, scheduled alerts.

Instead of requiring users to manually configure an API, parameters, polling frequency, and notification logic, PingMe uses an **LLM + LangGraph planning pipeline** to understand the request, resolve missing parameters, select the appropriate data source, verify the API call against the live service, and automatically schedule the alert.

When the condition is satisfied, PingMe sends a notification through Telegram and automatically deactivates the alert.

---

## Example

A user can simply say:

> "Notify me when Bitcoin drops below $90,000. Check every 2 minutes."

PingMe converts this into:

```text
Intent        → crypto_price
Connector     → CoinGecko
Parameters    → coin_id=bitcoin, currency=usd
Condition     → price < 90000
Interval      → 120 seconds
Verification  → Live CoinGecko API call
Notification  → Telegram
```

Once Bitcoin satisfies the condition:

```text
Bitcoin price < $90,000
        ↓
Telegram notification
        ↓
Trigger deactivated
```

The alert is **one-shot**: it fires once and does not continuously re-arm.

---

# Architecture

```text
                         ┌─────────────────────┐
                         │       User          │
                         │ Natural-language    │
                         │      request        │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │     FastAPI API     │
                         │      POST /plan     │
                         └──────────┬──────────┘
                                    │
                                    ▼
                     ┌────────────────────────────┐
                     │       LangGraph Planner     │
                     │                            │
                     │  Understand Query           │
                     │       ↓                    │
                     │  Search Connector Registry │
                     │       ↓                    │
                     │  Fill Parameters + Tools   │
                     │       ↓                    │
                     │  Validate Parameters       │
                     │       ↓                    │
                     │  Resolve Interval          │
                     │       ↓                    │
                     │  Verify Live API           │
                     └──────────────┬─────────────┘
                                    │
                              Verified plan
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │     PostgreSQL /    │
                         │       SQLite        │
                         │      Triggers       │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │    Celery Beat      │
                         │   Dispatch Tick     │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │    Redis Broker     │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │   Celery Worker     │
                         │                     │
                         │ Fetch → Evaluate    │
                         │       → Notify      │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │  External API       │
                         │  CoinGecko /        │
                         │  Open-Meteo / etc.  │
                         └──────────┬──────────┘
                                    │
                              Condition true
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │  Telegram Provider  │
                         └─────────────────────┘
```

---

# Key Features

### 1. Natural-language alert creation

Users don't need to know which API to call.

```text
"Notify me when Bitcoin falls below $90,000"
```

is converted into a structured alert configuration.

---

### 2. Agentic planning with LangGraph

The planning process is represented as a graph rather than a single LLM call.

```text
START
  │
  ▼
Understand Query
  │
  ▼
Search Registry
  │
  ├── unsupported → Discovery
  │
  ▼
Fill Parameters
  │
  ▼
Check Parameters
  │
  ▼
Resolve Interval
  │
  ▼
Verify Request
  │
  ├── success ──────────→ END
  │
  └── failure
        │
        ▼
   Self-Correction
        │
        └────────→ Fill Parameters
```

This allows the system to **observe failures and retry parameter resolution** rather than blindly trusting the first LLM-generated API configuration.

---

# 3. Automatic Parameter Resolution

Different APIs require different parameters.

For example:

```text
"Notify me when the AQI in Delhi exceeds 100"
```

The Open-Meteo API requires:

```text
latitude
longitude
```

The user doesn't have to provide those coordinates manually.

PingMe uses a tool:

```text
geocode_location()
```

to convert:

```text
Delhi
```

into:

```text
latitude  = 28.65195
longitude = 77.23149
```

The parameter-resolution agent can therefore combine:

```text
User input
    +
LLM-extracted entities
    +
External tools
    +
Previous verification failures
```

to construct the final API parameters.

If the system cannot safely resolve a parameter, it asks the user instead of inventing a value.

---

# 4. Live API Verification

PingMe does not simply assume that an API configuration is valid.

Before creating a trigger, the planner actually calls the selected connector:

```text
Planner
   ↓
Build parameters
   ↓
connector.fetch()
   ↓
Real external API
   ↓
Extract value
```

For example:

```text
coin_id = bitcoin
currency = usd
```

is tested against CoinGecko before the alert is persisted.

This catches problems such as:

* Invalid API parameters
* Incorrect coordinates
* Invalid repository names
* Incorrect response paths
* Unsupported values
* API configuration errors

The planner can then feed the failure back into the parameter-resolution step and retry.

---

# 5. Self-Correcting Planning Loop

If verification fails, PingMe doesn't immediately give up.

Example:

```text
LLM guesses parameter
        ↓
Live API call
        ↓
API returns error
        ↓
Error added to planner context
        ↓
Parameter agent tries again
        ↓
Live API verification
```

The system is therefore closer to:

```text
Plan → Execute → Observe → Correct
```

rather than:

```text
Prompt → Guess → Hope
```

---

# 6. Connector Architecture

All external APIs implement a common `Connector` interface.

Each connector defines:

```python
name
description
capabilities
parameters
value_field
min_interval_seconds
default_interval_seconds
```

and implements:

```python
build_request()
extract_value()
```

The base class provides the common:

```python
fetch()
```

pipeline:

```text
build_request()
      ↓
HTTP request
      ↓
response.json()
      ↓
extract_value()
      ↓
numeric value
```

This creates a **single source of truth** between the planner and scheduler.

The planner uses connector metadata to understand what an API can do, while the worker uses the same connector to actually call it.

---

# Supported Connectors

The project currently includes connectors for:

| Connector          | Capability           | Example                      |
| ------------------ | -------------------- | ---------------------------- |
| CoinGecko          | Cryptocurrency price | Bitcoin price                |
| Open-Meteo Weather | Temperature          | Delhi temperature            |
| Open-Meteo Air     | Air quality          | Delhi AQI                    |
| GitHub             | Repository stars     | `openai/openai-python` stars |
| USGS               | Earthquake magnitude | Latest earthquake            |
| DynamicConnector   | Config-driven APIs   | Runtime API registration     |

---

# Dynamic Connectors

PingMe can also create connectors without writing a new Python class.

A `DynamicConnector` is defined using configuration such as:

```json
{
  "name": "example_api",
  "base_url": "https://api.example.com/data",
  "method": "GET",
  "parameters": {},
  "response_path": "data.value"
}
```

JMESPath is used to extract the required value:

```text
API response
     ↓
JMESPath
     ↓
value
```

This makes the connector layer extensible without requiring a deployment for every simple GET-based API.

Dynamic connector configurations are persisted in the database and loaded again when the application starts.

---

# API Discovery

For unsupported requests, PingMe has an optional discovery path.

```text
User request
     ↓
No registered connector
     ↓
Search API registry
     ↓
Find candidate APIs
     ↓
Read API specification
     ↓
LLM proposes connector configuration
     ↓
User confirmation
     ↓
DynamicConnector
```

Discovery is disabled by default:

```env
ENABLE_DISCOVERY=false
```

This is intentional because automatically discovering arbitrary APIs introduces additional reliability and security considerations.

---

# Interval Resolution

Users can specify their desired frequency:

```text
"check every 2 minutes"
```

PingMe converts this to:

```text
120 seconds
```

However, every connector has a minimum safe interval.

For example:

```text
User requested: 10 seconds
Connector minimum: 60 seconds

Final interval: 60 seconds
```

If the user doesn't specify a frequency, the connector's default interval is used.

This prevents unnecessarily aggressive polling of external APIs.

---

# Scheduling Architecture

PingMe uses **Celery + Redis** for the actual background execution path.

There are two separate processes:

### Celery Beat

Beat periodically runs:

```text
dispatch_due_triggers
```

It finds triggers satisfying:

```text
active = true
AND
next_check_at <= now
```

and places their IDs onto the Redis-backed Celery queue.

### Celery Worker

Workers consume:

```text
check_trigger_task
```

and perform:

```text
Fetch
  ↓
Evaluate condition
  ↓
Update database
  ↓
Notify if matched
```

This separates scheduling from execution.

```text
Celery Beat
    │
    ▼
Redis
    │
    ▼
Celery Worker
```

A slow API request therefore doesn't block the scheduler itself.

---

# Preventing Duplicate Dispatch

There is an important race condition in a distributed scheduler.

Suppose:

```text
Beat interval = 5 seconds
API request = 12 seconds
```

Without protection:

```text
t=0    trigger dispatched
t=5    trigger still appears due → dispatched again
t=10   trigger still appears due → dispatched again
```

PingMe prevents this by **claiming the trigger before execution**.

When a trigger is claimed:

```text
next_check_at = now + interval
```

is immediately persisted.

Therefore, the next Beat tick sees the trigger as no longer due.

The worker later updates the value again after the actual check completes.

---

# One-Shot Alerts

PingMe treats alerts as one-shot events.

When the condition becomes true:

```text
condition = true
      ↓
send notification
      ↓
triggered_at = now
      ↓
active = false
```

The trigger will not fire again.

For example:

```text
Notify me when Bitcoin > $100,000
```

Once Bitcoin reaches $100,000:

```text
Telegram → sent
Trigger  → inactive
```

No repeated notifications are generated.

---

# Failure Handling

External APIs can fail due to:

* Network timeouts
* Connection errors
* Temporary upstream failures
* Invalid configuration
* API errors

Transient failures are retried within a single check using exponential-style backoff:

```text
Attempt 1
   ↓
2 seconds
   ↓
Attempt 2
   ↓
8 seconds
   ↓
Attempt 3
   ↓
20 seconds
   ↓
Failure persisted
```

A trigger also tracks:

```text
consecutive_failures
last_error
last_checked_at
```

If the number of consecutive failures reaches:

```env
MAX_CONSECUTIVE_FAILURES
```

the trigger is automatically deactivated.

This prevents a broken alert from retrying indefinitely.

---

# Notification System

Notifications use a provider abstraction:

```text
NotificationProvider
        │
        └── TelegramProvider
```

The trigger stores:

```json
{
  "channel": "telegram"
}
```

The registry resolves the appropriate provider:

```python
get_provider("telegram")
```

Telegram is optional during development.

If Telegram credentials are not configured, PingMe prints the notification to the worker console instead.

---

# Database Model

The central database entity is the `Trigger`.

A trigger contains:

```text
id
name
source
config
condition
notification
interval_seconds
active
last_checked_at
next_check_at
last_value
triggered_at
consecutive_failures
last_error
created_at
```

Example:

```json
{
  "source": "coingecko",
  "config": {
    "coin_id": "bitcoin",
    "currency": "usd"
  },
  "condition": {
    "field": "price",
    "operator": "lt",
    "value": 90000
  },
  "interval_seconds": 120,
  "active": true
}
```

---

# Project Structure

```text
pingme-unified/
│
├── agent/
│   ├── planner.py
│   ├── parameter_filler.py
│   ├── interval_resolver.py
│   ├── discovery.py
│   ├── schemas.py
│   └── tools.py
│
├── connectors/
│   ├── base.py
│   ├── registry.py
│   ├── coingecko.py
│   ├── open_meteo_air.py
│   ├── open_meteo_weather.py
│   ├── github.py
│   ├── usgs.py
│   └── dynamic.py
│
├── notifications/
│   ├── base.py
│   ├── registry.py
│   └── telegram.py
│
├── celery_app.py
├── tasks.py
├── worker.py
├── scheduler.py
├── main.py
├── models.py
├── database.py
├── rules.py
├── config.py
│
├── requirements.txt
├── render.yaml
└── .env.example
```

---

# Running Locally

## 1. Create virtual environment

### Linux/macOS

```bash
python -m venv .venv
source .venv/bin/activate
```

### Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

---

## 2. Install dependencies

```bash
pip install -r requirements.txt
```

---

## 3. Configure environment variables

Create `.env`:

```env
GROQ_API_KEY=your_groq_api_key

MODEL_NAME=openai/gpt-oss-120b

DATABASE_URL=sqlite+aiosqlite:///./pingme.db

REDIS_URL=redis://localhost:6379/0

TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

SCHEDULER_POLL_SECONDS=5

MAX_CONSECUTIVE_FAILURES=10

ENABLE_DISCOVERY=false
```

For an Upstash Redis instance, use a TLS URL such as:

```env
REDIS_URL=rediss://default:PASSWORD@HOST:6379/0?ssl_cert_reqs=required
```

---

# Running the System

PingMe's Celery architecture consists of four components:

```text
FastAPI
Celery Worker
Celery Beat
Redis
```

### Terminal 1 — Redis

```bash
redis-server
```

### Terminal 2 — FastAPI

```bash
uvicorn main:app --reload
```

### Terminal 3 — Celery Worker

For Windows development:

```powershell
celery -A celery_app worker --loglevel=info --pool=solo
```

On Linux/macOS, the standard worker can be used:

```bash
celery -A celery_app worker --loglevel=info
```

### Terminal 4 — Celery Beat

```bash
celery -A celery_app beat --loglevel=info
```

---

# Creating an Alert

Send:

```bash
curl -X POST http://localhost:8000/plan \
  -H "Content-Type: application/json" \
  -d "{\"query\":\"notify me when bitcoin drops below 90000 usd, check every 2 minutes\"}"
```

A successful response contains a verified plan and trigger information.

Then the background system takes over:

```text
Trigger persisted
      ↓
Beat detects due trigger
      ↓
Celery task queued
      ↓
Worker executes
      ↓
API fetched
      ↓
Condition evaluated
      ↓
Telegram notification
```

---

# Useful API Endpoints

### Health

```http
GET /health
```

### Create an alert

```http
POST /plan
```

Example:

```json
{
  "query": "notify me when bitcoin drops below 90000 usd"
}
```

### List triggers

```http
GET /triggers
```

### Modify a trigger

```http
PATCH /triggers/{id}
```

### Delete a trigger

```http
DELETE /triggers/{id}
```

### Manually check a trigger

```http
POST /triggers/{id}/check-now
```

This is useful for testing the complete:

```text
API → condition → notification
```

pipeline without waiting for the scheduler.

### Free-hosting tick endpoint

```http
POST /tick?secret=YOUR_SECRET
```

This endpoint is intended for the free Render deployment mode where an external cron service replaces Celery Beat.

---

# Free Deployment Architecture

The full Celery architecture requires an always-running worker, which is not suitable for some free PaaS configurations.

PingMe therefore includes an alternative deployment mode:

```text
cron-job.org
      │
      ▼
Render Web Service
      │
      ├── claim_due_triggers()
      │
      └── execute_trigger_once()
              │
              ▼
          External APIs
              │
              ▼
           Telegram
```

The hosted version can use:

```text
Render
+
Neon PostgreSQL
+
cron-job.org
+
Telegram
```

while the local/development architecture uses:

```text
FastAPI
+
Celery Beat
+
Celery Worker
+
Redis
+
SQLite/PostgreSQL
```

The important point is that both paths reuse the same core scheduling and trigger-execution logic.

---

# Design Decisions

## Why LangGraph?

The planning process contains multiple dependent steps:

```text
Understand
   ↓
Select source
   ↓
Resolve parameters
   ↓
Validate
   ↓
Verify
   ↓
Retry if necessary
```

LangGraph makes these transitions explicit and allows conditional routing and loops.

---

## Why Redis + Celery?

The API should not perform long-running periodic work itself.

Instead:

```text
API
 ↓
Database
 ↓
Celery Beat
 ↓
Redis
 ↓
Worker
```

This provides separation between:

* Request handling
* Scheduling
* Queueing
* Background execution

Workers can also be scaled independently when the workload grows.

---

## Why verify before scheduling?

Without verification:

```text
LLM generates API configuration
        ↓
Store it
        ↓
Discover days later that it was invalid
```

PingMe instead uses:

```text
LLM generates configuration
        ↓
Live API verification
        ↓
Only then persist trigger
```

This moves errors to the creation phase rather than discovering them during background execution.

---

## Why one-shot alerts?

The primary user intent is:

> "Notify me when X happens."

Once X happens, the job is complete.

Therefore:

```text
condition false → keep checking
condition true  → notify + deactivate
```

This also avoids unnecessary repeated notifications and complicated re-arming logic.

---

# Technology Stack

| Component               | Technology        |
| ----------------------- | ----------------- |
| API                     | FastAPI           |
| Agent orchestration     | LangGraph         |
| LLM                     | Groq              |
| LLM integration         | LangChain         |
| Background jobs         | Celery            |
| Scheduler               | Celery Beat       |
| Message broker          | Redis             |
| Database                | SQLAlchemy        |
| Local database          | SQLite            |
| Production database     | PostgreSQL / Neon |
| HTTP client             | HTTPX             |
| Dynamic JSON extraction | JMESPath          |
| Notifications           | Telegram Bot API  |
| Deployment              | Render            |
| External scheduling     | cron-job.org      |

---

# Current Limitations

PingMe is designed as a portfolio/engineering project and intentionally has some limitations.

### Session state

Planner sessions are currently stored in application memory:

```python
sessions: dict[str, dict]
```

A production deployment with multiple API instances would move this state to Redis or PostgreSQL.

### Dynamic API discovery

Discovery is optional and disabled by default.

```env
ENABLE_DISCOVERY=false
```

The built-in connector path is the primary verified path.

### Connector scope

`DynamicConnector` currently targets relatively simple JSON GET APIs.

More complex APIs involving:

* OAuth
* POST request bodies
* pagination
* multi-step workflows

would require a dedicated connector implementation.

### Local Windows Celery

Windows development can encounter multiprocessing issues with Celery's default worker pool. For local Windows development, use:

```powershell
celery -A celery_app worker --loglevel=info --pool=solo
```

Production Linux deployments can use Celery's normal worker pool.

---

# Future Improvements

Potential next steps include:

* Redis-backed planner sessions
* Authentication and user-specific triggers
* Multiple notification channels
* Email / Slack / Discord providers
* Connector health monitoring
* Rate-limit-aware scheduling
* Distributed worker scaling
* Persistent execution history
* Dead-letter queues
* API authentication management
* OAuth-aware dynamic connectors
* More sophisticated API discovery
* Connector versioning
* Observability with Prometheus/OpenTelemetry
* Dashboard for active triggers and execution history

---

# Core Idea

PingMe's central design principle is:

```text
Natural Language
      ↓
Understand
      ↓
Select
      ↓
Resolve
      ↓
Verify
      ↓
Schedule
      ↓
Execute
      ↓
Evaluate
      ↓
Notify
```

The goal is to make API-driven alerting feel less like configuring a monitoring system and more like simply telling an agent:

> **"Ping me when this happens."**
