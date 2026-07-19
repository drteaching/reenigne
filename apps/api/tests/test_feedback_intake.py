"""
Feedback intake: caps, rate limits, secret rejection, honeypot.

Intake is a public write path, so every guard here is load-bearing. The
secret scanner in particular has to reject *and explain*: a bug report
bounced for an unexplained reason is a bug report we never receive.
"""

import uuid

import pytest
from sqlalchemy import delete, select

from app.feedback import Feedback
from app.db import SessionLocal
from app.triage import FeedbackTriageJob
from conftest import make_user


@pytest.fixture
def portal():
    from anyio.from_thread import start_blocking_portal

    with start_blocking_portal() as p:
        yield p


async def _clear_feedback():
    async with SessionLocal() as s:
        await s.execute(delete(FeedbackTriageJob))
        await s.execute(delete(Feedback))
        await s.commit()


@pytest.fixture(autouse=True)
def clean_feedback(client, portal):
    portal.call(_clear_feedback)
    yield


async def _count_rows() -> int:
    async with SessionLocal() as s:
        return len((await s.execute(select(Feedback))).scalars().all())


async def _all_rows():
    async with SessionLocal() as s:
        return (await s.execute(select(Feedback))).scalars().all()


def _body(**kw):
    body = {
        "kind": "bug",
        "title": "Recording stops after 30 seconds",
        "description": "Every session ends early on macOS 15.",
    }
    body.update(kw)
    return body


def _submit(client, headers=None, **kw):
    return client.post("/v1/feedback", headers=headers or {}, json=_body(**kw))


# ---------- Happy paths ----------


def test_authenticated_submission_is_stored(client, portal):
    _, headers, user_id = make_user(f"fb-{uuid.uuid4().hex[:6]}@example.com")
    resp = _submit(client, headers)

    assert resp.status_code == 202, resp.text
    assert resp.json()["status"] == "received"

    rows = portal.call(_all_rows)
    assert len(rows) == 1
    assert rows[0].user_id == user_id
    assert rows[0].kind == "bug"
    assert rows[0].status == "received"


def test_anonymous_submission_is_stored_without_a_user(client, portal):
    resp = _submit(client, kind="improvement")
    assert resp.status_code == 202, resp.text

    rows = portal.call(_all_rows)
    assert len(rows) == 1
    assert rows[0].user_id is None
    assert rows[0].kind == "improvement"


def test_context_is_captured(client, portal):
    _, headers, _ = make_user(f"ctx-{uuid.uuid4().hex[:6]}@example.com")
    _submit(
        client,
        headers,
        context={
            "app_version": "0.2.0",
            "platform": "darwin",
            "os": "macOS 15.1",
            "logs_excerpt": "[worker] started\n[worker] ok",
        },
    )
    row = portal.call(_all_rows)[0]
    import json

    ctx = json.loads(row.context_json)
    assert ctx["app_version"] == "0.2.0"
    assert "logs_excerpt" in ctx


def test_invalid_kind_rejected(client):
    assert _submit(client, kind="feature-request").status_code == 422


# ---------- Length caps ----------


def test_title_cap_enforced(client, portal):
    assert _submit(client, title="x" * 201).status_code == 422
    assert portal.call(_count_rows) == 0


def test_description_cap_enforced(client, portal):
    assert _submit(client, description="x" * 5001).status_code == 422
    assert portal.call(_count_rows) == 0


def test_logs_excerpt_cap_enforced(client, portal):
    resp = _submit(client, context={"logs_excerpt": "x" * 10001})
    assert resp.status_code == 422
    assert portal.call(_count_rows) == 0


def test_caps_are_enforced_at_the_boundary_not_by_the_client(client, portal):
    """Exactly at the limit is accepted; one over is not."""
    assert _submit(client, title="x" * 200).status_code == 202
    assert _submit(client, title="x" * 201).status_code == 422


# ---------- Secret rejection ----------


# Assembled at runtime rather than written as literals.
#
# These are synthetic, but a literal `sk_live_...` or `ghp_...` in a committed
# file is enough to trip GitHub's push protection and platform secret
# scanners -- which is correct of them, and would block every push of this
# repo. Splitting the prefix keeps the scanner regexes under test (they see
# the assembled string at runtime) without shipping something that reads as a
# live credential at rest.
_FILLER = "abcdefghijklmnopqrstuvwxyz012345"

SECRETS = [
    ("Authorization: Bearer " + _FILLER[:16], "authorization header"),
    ("my key is " + "sk" + "-" + _FILLER, "api key"),
    ("STRIPE=" + "sk" + "_live_" + _FILLER[:24], "api key"),
    ("XAI=" + "xai" + "-" + _FILLER, "api key"),
    ("token " + "ghp" + "_" + _FILLER + "6789", "github token"),
    ("wh" + "sec_" + _FILLER[:29], "webhook signing secret"),
    (
        "ey" + "JhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVPmB92K27u",
        "json web token",
    ),
]


@pytest.mark.parametrize("payload,expected_name", SECRETS)
def test_secret_bearing_submission_is_rejected(client, portal, payload, expected_name):
    resp = _submit(client, description=f"Here is my config: {payload}")
    assert resp.status_code == 400, resp.text
    assert portal.call(_count_rows) == 0, "a rejected secret was stored anyway"


@pytest.mark.parametrize("payload,expected_name", SECRETS)
def test_rejection_names_the_pattern_and_says_what_to_do(
    client, payload, expected_name
):
    """
    A bounced report with an unexplained reason is a lost report. The user
    must learn which pattern matched and that redacting lets them resubmit.
    """
    detail = _submit(client, description=f"config: {payload}").json()["detail"]
    lowered = detail.lower()
    assert expected_name in lowered, (
        f"rejection must name the matched pattern; got: {detail}"
    )
    assert "redact" in lowered, f"rejection must say what to do; got: {detail}"


def test_secret_in_title_is_rejected(client):
    assert _submit(client, title="sk" + "-" + _FILLER).status_code == 400


def test_secret_in_logs_excerpt_is_rejected(client):
    resp = _submit(
        client, context={"logs_excerpt": "Authorization: Bearer abcdefghijklmnop"}
    )
    assert resp.status_code == 400


def test_innocent_log_fragment_is_not_a_false_positive(client, portal):
    """
    A bare eyJ or the word 'sk-' in prose must not bounce a real report. The
    JWT pattern requires the full three-part structure for this reason.
    """
    resp = _submit(
        client,
        description=(
            "Log said: base64 blob eyJ truncated here, and the sk- prefix "
            "appears in our docs. Also saw Authorization redacted by the app."
        ),
    )
    assert resp.status_code == 202, resp.text
    assert portal.call(_count_rows) == 1


# ---------- Honeypot ----------


def test_honeypot_submission_returns_200_but_is_discarded(client, portal):
    resp = client.post("/v1/feedback", json=_body(website="http://spam.example"))
    assert resp.status_code == 202, "honeypot must look like success to the bot"
    assert portal.call(_count_rows) == 0, "honeypot submission was stored"


def test_empty_honeypot_field_is_fine(client, portal):
    assert client.post("/v1/feedback", json=_body(website="")).status_code == 202
    assert portal.call(_count_rows) == 1


# ---------- Rate limits ----------


def test_authenticated_rate_limit(client, portal, settings):
    _, headers, _ = make_user(f"rate-{uuid.uuid4().hex[:6]}@example.com")
    limit = settings.feedback_max_per_user_per_day

    for i in range(limit):
        assert _submit(client, headers, title=f"Report {i}").status_code == 202

    resp = _submit(client, headers, title="One too many")
    assert resp.status_code == 429
    assert portal.call(_count_rows) == limit


def test_anonymous_rate_limit_is_per_ip(client, portal, settings):
    limit = settings.feedback_max_per_ip_per_day
    for i in range(limit):
        assert _submit(client, title=f"Anon {i}").status_code == 202
    assert _submit(client, title="Over").status_code == 429
    assert portal.call(_count_rows) == limit


def test_rate_limits_are_scoped_per_user(client, portal, settings):
    """One user exhausting their allowance must not block another."""
    _, first, _ = make_user(f"a-{uuid.uuid4().hex[:6]}@example.com")
    _, second, _ = make_user(f"b-{uuid.uuid4().hex[:6]}@example.com")

    for _ in range(settings.feedback_max_per_user_per_day):
        _submit(client, first)
    assert _submit(client, first).status_code == 429
    assert _submit(client, second).status_code == 202


def test_submitter_ip_is_not_stored_in_the_clear(client, portal):
    """We keep an HMAC to count, not a location log."""
    _submit(client)
    row = portal.call(_all_rows)[0]
    assert row.submitter_ip_hash, "no hash recorded; anonymous limits cannot work"
    # TestClient's client address; must not appear verbatim anywhere on the row.
    for value in (row.submitter_ip_hash, row.context_json or ""):
        assert "testclient" not in value
        assert "127.0.0.1" not in value


def test_feedback_never_touches_quota_or_credits(client, portal):
    """Intake is not billable in any way."""
    _, headers, user_id = make_user(f"free-{uuid.uuid4().hex[:6]}@example.com")

    async def _snapshot():
        from app.db import User

        async with SessionLocal() as s:
            u = (await s.execute(select(User).where(User.id == user_id))).scalar_one()
            return (u.analyses_used_month, u.minutes_used_month, u.credits)

    before = portal.call(_snapshot)
    assert _submit(client, headers).status_code == 202
    assert portal.call(_snapshot) == before
