"""Database — Supabase Postgres (asyncpg) or local SQLite."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, Integer, NullPool, String, Uuid, select, text
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

    # Native UUID on Postgres (matching the migration and the auth.users FK);
    # CHAR(32) on SQLite. as_uuid=False keeps the Python side a plain string,
    # so callers and JSON responses are unchanged.
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
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
    # Completed analyses this period. Charged on success, never reserved, so
    # this only ever counts work the user actually received.
    analyses_used_month: Mapped[int] = mapped_column(Integer, default=0)
    usage_month: Mapped[str] = mapped_column(String(7), default="")
    # Purchased one-off balance. Not period-scoped: the monthly reset must
    # never touch it, and a refund is never guarded by a usage month.
    credits: Mapped[int] = mapped_column(Integer, default=0)


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
elif _settings.db_null_pool:
    _engine_kwargs["poolclass"] = NullPool
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
    if not is_uuid(user_id):
        return None
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


def is_uuid(value: str | None) -> bool:
    """
    True if `value` can be used against a uuid column.

    Required at every boundary that accepts an identifier from outside. On
    Postgres the driver encodes the parameter as a UUID and raises on
    anything else, turning an unvalidated path segment or JWT subject into a
    500. SQLite accepts the same input silently, so this cannot be left to
    the database to catch.
    """
    if not value:
        return False
    try:
        UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return False
    return True
