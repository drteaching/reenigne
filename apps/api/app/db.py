"""Database — Supabase Postgres (asyncpg) or local SQLite."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import DateTime, Float, NullPool, String, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .config import get_settings


class Base(DeclarativeBase):
    pass


class User(Base):
    """
    Maps to public.profiles on Supabase.
    Local SQLite uses the same shape (id as string UUID).
    """

    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    # Only used for local/dev auth (not populated under Supabase Auth)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    subscription_status: Mapped[str] = mapped_column(String(64), default="none")
    subscription_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    plan: Mapped[str] = mapped_column(String(64), default="free")
    minutes_used_month: Mapped[float] = mapped_column(Float, default=0.0)
    usage_month: Mapped[str] = mapped_column(String(7), default="")


def _normalize_database_url(url: str) -> str:
    """Accept postgres:// / postgresql:// and force asyncpg driver."""
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    # Supabase pooler often needs SSL
    if "supabase.co" in url and "ssl" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}ssl=require"
    return url


_settings = get_settings()
_db_url = _normalize_database_url(_settings.database_url)

# Supabase's transaction pooler (port 6543) is pgbouncer in transaction mode.
# Pooling on top of it — and asyncpg's implicit prepared-statement cache —
# causes "prepared statement already exists" errors, so disable both there.
_is_transaction_pooler = "pooler.supabase.com:6543" in _db_url

_engine_kwargs: dict = {"echo": False}
if _is_transaction_pooler:
    _engine_kwargs["poolclass"] = NullPool
    _engine_kwargs["connect_args"] = {"statement_cache_size": 0}
else:
    _engine_kwargs["pool_pre_ping"] = True

engine = create_async_engine(_db_url, **_engine_kwargs)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db():
    """Create tables for local SQLite; on Supabase schema comes from migrations."""
    url = get_settings().database_url
    if url.startswith("sqlite"):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    else:
        # Ensure we can connect; schema managed by supabase/migrations
        async with engine.begin() as conn:
            await conn.execute(text("select 1"))


async def get_session():
    async with SessionLocal() as session:
        yield session


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email.lower()))
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: str) -> User | None:
    result = await session.execute(select(User).where(User.id == str(user_id)))
    return result.scalar_one_or_none()


async def ensure_profile(
    session: AsyncSession,
    *,
    user_id: str,
    email: str,
) -> User:
    user = await get_user_by_id(session, user_id)
    if user:
        return user
    user = User(
        id=str(user_id),
        email=email.lower(),
        usage_month=datetime.now(timezone.utc).strftime("%Y-%m"),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def new_local_user_id() -> str:
    return str(uuid4())
