from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import settings
from models import Base

# SQLite for a true zero-setup local run — no Postgres/Docker needed to
# demo this. Swapping to Postgres later (Neon, etc.) is a one-line change:
# set DATABASE_URL to a postgresql+asyncpg:// URL. SQLAlchemy async handles
# both; nothing else in this file or in models.py needs to change.
engine = create_async_engine(settings.database_url, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    async with SessionLocal() as session:
        yield session
