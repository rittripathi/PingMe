from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    groq_api_key: str
    model_name: str = "openai/gpt-oss-120b"

    database_url: str = "sqlite+aiosqlite:///./pingme.db"

    # Local dev default. For deployment, Upstash Redis's free tier gives
    # a rediss:// URL — drop it in here directly, both Celery and redis-py
    # accept it as-is.
    redis_url: str = "redis://localhost:6379/0"

    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    scheduler_poll_seconds: int = 5
    max_consecutive_failures: int = 10  # deactivate a trigger after this many failed checks in a row

    # Shared secret for the /tick endpoint (the free-hosting path — see
    # README). Without one, anyone who finds the URL can trigger real
    # external API calls and DB writes on your behalf. Set this before
    # exposing /tick publicly; cron-job.org sends it as a query param.
    tick_secret: str | None = None

    # Off by default — the live apis.guru + LLM-reads-a-spec discovery
    # path (agent/discovery.py) is unverified from the environment this
    # was built in. Flip on once you've tried it against your own key.
    enable_discovery: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
