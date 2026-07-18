"""
Malformed identifiers must be rejected cleanly, not crash the request.

Once the id columns are real uuid on Postgres, asyncpg encodes the parameter
itself and raises on anything that is not a UUID. SQLAlchemy's asyncpg bind
processor passes the string straight through, so an unvalidated path id or
JWT subject surfaces as a 500 rather than a 404/401. SQLite silently accepts
the same input, so only the Postgres run would show it.
"""

import jwt
import pytest

from app.config import get_settings

MALFORMED = [
    "not-a-uuid",
    "12345",
    "../../etc/passwd",
    "'; drop table analysis_jobs; --",
    "6f1a3c2e-0000-4000-8000",  # truncated
    "zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz",  # right shape, invalid hex
]


@pytest.mark.parametrize("job_id", MALFORMED)
def test_malformed_job_id_returns_404(client, user, job_id):
    _, headers = user
    resp = client.get(f"/v1/analyze/jobs/{job_id}", headers=headers)
    assert resp.status_code == 404, (
        f"expected 404 for {job_id!r}, got {resp.status_code}: {resp.text[:200]}"
    )


def test_wellformed_but_unknown_job_id_returns_404(client, user):
    _, headers = user
    resp = client.get(
        "/v1/analyze/jobs/6f1a3c2e-0000-4000-8000-000000000000", headers=headers
    )
    assert resp.status_code == 404


@pytest.mark.parametrize("subject", ["not-a-uuid", "12345", ""])
def test_token_with_malformed_subject_returns_401(client, subject):
    """
    A validly signed token whose `sub` is not a uuid must be rejected as
    unauthenticated, not blow up the user lookup.
    """
    settings = get_settings()
    token = jwt.encode(
        {"sub": subject, "email": "someone@example.com"},
        settings.api_secret_key,
        algorithm="HS256",
    )
    resp = client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401, (
        f"expected 401 for sub={subject!r}, got {resp.status_code}: "
        f"{resp.text[:200]}"
    )
