from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)

async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    """FastAPI dependency — request-scoped session. Closed as soon as the response
    is sent, so it must never be handed to a BackgroundTask that outlives the request
    (background research runs open their own session via async_session_maker)."""
    async with async_session_maker() as session:
        yield session
