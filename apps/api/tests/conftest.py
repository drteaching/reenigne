"""
Test environment. These vars must be set before `app` is imported: db.py
builds its engine at module scope and get_settings() is lru_cached, so any
later change would not take effect.

Runs against SQLite by default. Set DATABASE_URL to a Postgres URL to run the
same suite against the real deployment backend — several classes of defect
(uuid vs varchar comparison, driver-level parameter encoding) simply cannot
occur on SQLite. See `make test-pg`.
"""

import os
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="reenigne-test-")

# Honour an externally supplied DATABASE_URL so the same suite can target
# Postgres; otherwise fall back to a throwaway SQLite file.
_DEFAULT_SQLITE = f"sqlite+aiosqlite:///{_TMP}/test.db"
DATABASE_URL = os.environ.get("DATABASE_URL") or _DEFAULT_SQLITE
IS_SQLITE = DATABASE_URL.startswith("sqlite")

os.environ.update(
    {
        "DATABASE_URL": DATABASE_URL,
        # Local JWT auth path (no Supabase) — must be a real key or the app
        # refuses to start, which is itself asserted in test_config.py.
        "API_SECRET_KEY": "test-only-secret-key-not-used-anywhere-real",
        "SUPABASE_URL": "",
        "SUPABASE_JWT_SECRET": "",
        "ENABLE_DEV_ENDPOINTS": "true",
        "STRIPE_SECRET_KEY": "",
        "OPENAI_API_KEY": "test-key",
        "XAI_API_KEY": "test-key",
        "PRO_MINUTES_PER_MONTH": "10",
        "PRO_MAX_FRAMES_PER_SESSION": "5",
        # The suite drives the app from several event loops (TestClient plus
        # blocking portals). asyncpg connections belong to the loop that
        # opened them, so pooling must be off or reuse across loops raises.
        "DB_NULL_POOL": "true",
        # The suite registers many users through the real endpoint; the
        # production 5/min cap would fail unrelated tests. test_rate_limit.py
        # lowers it deliberately for the cases that exercise it.
        "AUTH_RATE_LIMIT_PER_MINUTE": "100000",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

# Belt and braces: this fixture issues DROP TABLE. Refuse to point it at
# anything that is not obviously a disposable test database.
_TEST_DB_MARKERS = ("test", "localhost", "127.0.0.1", "postgres@", ":55432", "/tmp")


def _assert_disposable(url: str) -> None:
    if url.startswith("sqlite"):
        return
    if not any(marker in url for marker in _TEST_DB_MARKERS):
        raise RuntimeError(
            f"Refusing to run destructive schema setup against {url!r}. "
            "The test suite drops and recreates every table. Point "
            "DATABASE_URL at a disposable database."
        )


REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"
SHIM_SQL = Path(__file__).resolve().parent / "support" / "supabase_shim.sql"


async def _reset_postgres_from_migrations(url: str) -> None:
    """
    Build the Postgres test schema by applying the real migrations.

    Deliberately not Base.metadata.create_all: that derives the schema from
    the models, so the models would trivially agree with it and a
    model/migration type divergence could never surface. Applying the actual
    migration SQL means the suite runs against the shape production will have.

    Uses asyncpg directly because these files contain multi-statement scripts
    and dollar-quoted function bodies, which SQLAlchemy's parameterised
    execution path will not accept.
    """
    import asyncpg

    dsn = url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(
            "drop schema if exists public cascade;"
            "drop schema if exists auth cascade;"
            "create schema public;"
        )
        await conn.execute(SHIM_SQL.read_text(encoding="utf-8"))
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            await conn.execute(path.read_text(encoding="utf-8"))
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def _schema():
    """
    Recreate the schema once per session.

    SQLite builds from the models (it has no migrations of its own and no
    distinct uuid type). Postgres builds from supabase/migrations via a small
    shim for the Supabase-managed `auth` objects, so the deployed schema is
    what gets exercised.
    """
    from anyio.from_thread import start_blocking_portal

    _assert_disposable(DATABASE_URL)

    async def _reset():
        if IS_SQLITE:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
                await conn.run_sync(Base.metadata.create_all)
        else:
            await _reset_postgres_from_migrations(DATABASE_URL)

    with start_blocking_portal() as portal:
        portal.call(_reset)
    yield


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """
    The limiter's window is process-global, so one test's requests would
    otherwise count against the next.
    """
    from app.ratelimit import reset

    reset()
    yield
    reset()


@pytest.fixture(scope="session")
def client(_schema):
    with TestClient(app) as c:
        yield c


def pytest_collection_modifyitems(config, items):
    """Apply the backend-specific skips."""
    if IS_SQLITE:
        skip = pytest.mark.skip(
            reason=(
                "postgres_only: needs real row locking (SELECT ... FOR "
                "UPDATE); SQLAlchemy omits it on SQLite"
            )
        )
        marker = "postgres_only"
    else:
        skip = pytest.mark.skip(
            reason=(
                "sqlite_only: exercises local password auth, which inserts "
                "directly into profiles — forbidden by the auth.users foreign "
                "key on the Supabase schema"
            )
        )
        marker = "sqlite_only"

    for item in items:
        if marker in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def settings():
    return get_settings()


_counter = {"n": 0}


async def _provision_via_auth_users(user_id: str, email: str) -> None:
    """
    Create a user the way production does on Postgres.

    profiles.id references auth.users(id), so a profile cannot be inserted
    directly against the Supabase schema. Supabase creates the auth user and
    the handle_new_user trigger creates the profile — this mirrors that, which
    also means the PG run exercises that trigger.
    """
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.execute(
            text(
                "insert into auth.users (id, email) "
                "values (cast(:id as uuid), :email) on conflict do nothing"
            ),
            {"id": user_id, "email": email},
        )


def _register(client):
    """
    Register a user and return (email, auth headers).

    SQLite uses the local registration endpoint. Postgres cannot: that path
    inserts straight into profiles, which the auth.users foreign key forbids.
    A token is minted directly instead, since local password auth is a
    dev-only path that does not exist on a Supabase deployment.
    """
    _counter["n"] += 1
    email = f"user{_counter['n']}@example.com"

    if IS_SQLITE:
        resp = client.post(
            "/v1/auth/register", json={"email": email, "password": "hunter2hunter2"}
        )
        assert resp.status_code == 200, resp.text
        return email, {"Authorization": f"Bearer {resp.json()['access_token']}"}

    return _provision_postgres_user(email)


def _provision_postgres_user(email: str) -> tuple[str, dict]:
    import uuid as _uuid

    from anyio.from_thread import start_blocking_portal

    from app.auth import create_access_token

    user_id = str(_uuid.uuid4())
    with start_blocking_portal() as portal:
        portal.call(_provision_via_auth_users, user_id, email)
    return email, {"Authorization": f"Bearer {create_access_token(user_id, email)}"}


def make_user(email: str | None = None) -> tuple[str, dict, str]:
    """
    Backend-aware user creation for tests that need the user id.

    Returns (email, headers, user_id).
    """
    import uuid as _uuid

    from anyio.from_thread import start_blocking_portal

    from app.auth import create_access_token

    _counter["n"] += 1
    email = email or f"direct{_counter['n']}@example.com"
    user_id = str(_uuid.uuid4())

    async def _create():
        if not IS_SQLITE:
            await _provision_via_auth_users(user_id, email)
            return
        from app.db import SessionLocal, User

        async with SessionLocal() as s:
            s.add(
                User(
                    id=user_id,
                    email=email,
                    subscription_status="active",
                    plan="pro",
                )
            )
            await s.commit()

    with start_blocking_portal() as portal:
        portal.call(_create)

    if not IS_SQLITE:
        # The trigger creates the profile with default entitlements; the
        # tests that use this helper expect an active subscription.
        _activate(user_id)

    return email, {"Authorization": f"Bearer {create_access_token(user_id, email)}"}, user_id


def _activate(user_id: str) -> None:
    from anyio.from_thread import start_blocking_portal
    from sqlalchemy import text

    async def _run():
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "update profiles set subscription_status='active', plan='pro' "
                    "where id = cast(:id as uuid)"
                ),
                {"id": user_id},
            )

    with start_blocking_portal() as portal:
        portal.call(_run)


@pytest.fixture
def user(client):
    """Register a fresh user and return (email, auth headers)."""
    return _register(client)


@pytest.fixture
def other_user(client):
    """
    A second, distinct user.

    Not derived from `user`: pytest caches fixtures per test, so requesting
    `user` and `subscribed_user` together yields the same account — which
    would silently make cross-user isolation tests pass for the wrong reason.
    """
    return _register(client)


@pytest.fixture
def subscribed_user(client, user):
    """A user with an active subscription, via the dev activation endpoint."""
    email, headers = user
    resp = client.post("/v1/dev/activate", headers=headers)
    assert resp.status_code == 200, resp.text
    return email, headers
