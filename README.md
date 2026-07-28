# PingMe — Phase 1

A unified alert platform: *"ping me when X happens."* This is **Phase 1** —
the foundation only. Nothing actually checks prices or sends alerts yet;
that's Phase 2 and Phase 3. Right now we're proving the skeleton works: you
can register, log in, and create/view/delete triggers through the API, and
your Telegram bot can message you.

## What's in this phase
- FastAPI app with a health check endpoint
- Postgres + Redis running in Docker
- JWT-based register / login
- Trigger CRUD endpoints (create / list / delete) — just stores data, no
  price-checking logic yet
- A one-off script to confirm your Telegram bot works

## 1. Set up your Python environment

```bash
python -m venv venv
source venv/bin/activate      # on Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Configure your environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in:
- `SECRET_KEY` — generate one with:
  `python -c "import secrets; print(secrets.token_hex(32))"`
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` — see "Set up Telegram" below.
  You can skip these for now and come back later — they're only needed for
  the test script, not for the API itself.

## 3. Start Postgres and Redis

```bash
docker compose up -d
```

Check they're running with `docker compose ps`.

## 4. Run the API

```bash
uvicorn app.main:app --reload
```

Open your browser to **http://localhost:8000/docs** — this is FastAPI's
automatic interactive API documentation. You can test every endpoint right
from this page without writing any code.

## 5. Try it out

1. In `/docs`, expand `POST /auth/register`, click "Try it out", and
   register with any email + password.
2. Expand `POST /auth/login`, log in with the same email + password, and
   copy the `access_token` from the response.
3. Click the **Authorize** button near the top of the page and paste in the
   token (usually just the raw token, sometimes as `Bearer <token>` —
   the page will tell you which format it wants).
4. Try `POST /triggers/` to create a trigger, e.g.:
   ```json
   {
     "asset": "bitcoin",
     "condition": "<",
     "target_value": 50000
   }
   ```
5. Try `GET /triggers/` — you should see the trigger you just created.

## 6. Set up Telegram (optional for now)

1. Open Telegram, search for **@BotFather**, send `/newbot`, and follow the
   prompts. You'll get a token like `123456789:ABCdefGhIJKlmNoPQRstuVWXyz`.
2. Send any message to your new bot (so it knows who you are).
3. Visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in your
   browser and find `"chat":{"id": ...}` in the response — that number is
   your chat ID.
4. Put both values into `.env` as `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
5. Run:
   ```bash
   python scripts/test_telegram.py
   ```
   You should get a message from your bot on Telegram.

## Project structure

```
pingme/
├── app/
│   ├── main.py                 # FastAPI app entry point
│   ├── database.py             # DB connection setup
│   ├── models.py                # Database tables (User, Trigger, TriggerEvent)
│   ├── schemas.py                # API request/response shapes
│   ├── auth.py                    # Password hashing + JWT logic
│   └── routers/
│       ├── auth_routes.py     # /auth/register, /auth/login
│       └── trigger_routes.py  # /triggers CRUD
├── scripts/
│   └── test_telegram.py       # one-off Telegram bot test
├── docker-compose.yml          # Postgres + Redis containers
├── requirements.txt
├── .env.example
└── .gitignore
```

## What's next (not in this phase)
- **Phase 2**: a `TriggerHandler` that actually fetches the bitcoin price
  and checks it against each trigger's condition.
- **Phase 3**: Celery + Celery Beat to run those checks on a schedule
  automatically, and a `Notifier` that sends the Telegram message when a
  trigger fires, logging each check to `trigger_events`.
