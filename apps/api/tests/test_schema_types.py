"""
Model and migration column types must agree.

The models originally declared these columns as String(36) while the
migrations declared them `uuid`. On Postgres that makes every lookup fail
with "operator does not exist: uuid = character varying". SQLite has no
distinct uuid type, so the whole test suite passed against it regardless —
the defect was structurally invisible until deploy.

These checks are static: they compare what the models would emit on the
Postgres dialect against what the migration SQL declares, so they catch
divergence on any backend, including SQLite-only runs.
"""

import re
from pathlib import Path

import pytest
from sqlalchemy.dialects import postgresql

from app.db import Base

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "supabase" / "migrations"

# (table, column) pairs that must be uuid end to end.
UUID_COLUMNS = [
    ("profiles", "id"),
    ("analysis_jobs", "id"),
    ("analysis_jobs", "user_id"),
    ("analysis_jobs", "lock_token"),
]


def _declared_types(table: str) -> dict[str, str]:
    """
    Map column name -> declared SQL type from the CREATE TABLE for `table`,
    across every migration file. Later files override earlier ones so an
    ALTER-based follow-up migration is reflected.
    """
    types: dict[str, str] = {}
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        sql = path.read_text(encoding="utf-8")

        match = re.search(
            rf"create table if not exists (?:public\.)?{table}\s*\((.*?)\n\);",
            sql,
            re.DOTALL | re.IGNORECASE,
        )
        if match:
            for line in match.group(1).splitlines():
                line = line.strip().rstrip(",")
                if not line or line.startswith("--") or line.startswith("constraint"):
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    types[parts[0]] = parts[1].lower()

        # A follow-up migration may change a type.
        for col, newtype in re.findall(
            rf"alter table (?:public\.)?{table}\s+alter column (\w+)\s+"
            rf"(?:set data )?type (\w+)",
            sql,
            re.IGNORECASE,
        ):
            types[col] = newtype.lower()

    return types


def test_migrations_directory_is_discoverable():
    """Guard the path math above — a wrong path would vacuously pass."""
    assert MIGRATIONS_DIR.is_dir(), MIGRATIONS_DIR
    assert list(MIGRATIONS_DIR.glob("*.sql")), "no migrations found"


@pytest.mark.parametrize("table,column", UUID_COLUMNS)
def test_model_column_renders_as_uuid_on_postgres(table, column):
    col = Base.metadata.tables[table].c[column]
    rendered = col.type.compile(dialect=postgresql.dialect()).upper()
    assert rendered == "UUID", (
        f"{table}.{column} renders as {rendered} on Postgres, but the "
        f"migration declares uuid. A varchar parameter against a uuid column "
        f"raises 'operator does not exist: uuid = character varying'."
    )


@pytest.mark.parametrize("table,column", UUID_COLUMNS)
def test_migration_declares_uuid(table, column):
    declared = _declared_types(table)
    assert column in declared, f"{column} not found in {table} migration"
    assert declared[column] == "uuid", (
        f"migration declares {table}.{column} as {declared[column]}, "
        f"but the model emits UUID"
    )


def test_profiles_id_stays_uuid_for_the_auth_users_fk():
    """
    profiles.id references auth.users(id), which Supabase defines as uuid.

    Postgres has no equality operator between text and uuid, so a text
    profiles.id cannot carry that foreign key at all — the constraint fails
    with "Key columns are of incompatible types". That is why the models were
    aligned to uuid rather than the migrations to text: the text direction
    would force dropping the FK and its ON DELETE CASCADE from auth.users.
    """
    assert _declared_types("profiles")["id"] == "uuid"

    profiles_sql = next(MIGRATIONS_DIR.glob("*_profiles.sql")).read_text(
        encoding="utf-8"
    )
    assert "references auth.users" in profiles_sql.lower(), (
        "the cascade from auth.users was dropped; if that is intended, "
        "update this test and document the orphaned-profile consequence"
    )
