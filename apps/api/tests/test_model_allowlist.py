"""
Model routing is an explicit allowlist, not substring guessing.

The previous classifier returned "openai" for anything it did not recognise,
so a typo became a live call that failed at the provider with an opaque
error — after the job had been queued, claimed and charged against a runner
invocation.
"""

import pytest

from app.config import Settings, get_settings
from app.llm import (
    UnknownModel,
    model_registry,
    provider_for,
    resolve_model_chain,
)


def _settings() -> Settings:
    return Settings(_env_file=None)


def test_registry_maps_every_configured_model():
    s = _settings()
    assert model_registry(s) == {
        s.grok_model: "grok",
        s.openai_model: "openai",
        s.anthropic_model: "anthropic",
        s.openai_mini_model: "openai",
    }


@pytest.mark.parametrize(
    "model,provider",
    [("grok-4", "grok"), ("gpt-4o", "openai"), ("claude-sonnet-4-5", "anthropic")],
)
def test_known_models_route_to_their_provider(model, provider):
    assert provider_for(model, _settings()) == provider


@pytest.mark.parametrize(
    "model",
    [
        "gpt4o",              # typo — previously routed to OpenAI and failed there
        "claude-3-opus",      # plausible but not allowlisted
        "grok-5",             # future model, not yet configured
        "gpt-4o-super",       # prefix of a real id
        "",                   # empty
        "../../etc/passwd",   # nonsense
        "grok-claude-mix",    # previously matched Anthropic on a coincidence
    ],
)
def test_unknown_models_are_rejected(model):
    with pytest.raises(UnknownModel):
        provider_for(model, _settings())


def test_rejection_lists_the_available_models():
    """A 400 that does not say what is allowed just costs another round trip."""
    with pytest.raises(UnknownModel) as e:
        provider_for("nope", _settings())
    for m in ("grok-4", "gpt-4o", "claude-sonnet-4-5"):
        assert m in str(e.value)


def test_chain_starts_with_the_requested_model():
    chain = resolve_model_chain("claude-sonnet-4-5", _settings())
    assert chain[0] == ("anthropic", "claude-sonnet-4-5")


def test_chain_appends_fallbacks_without_duplicates():
    chain = resolve_model_chain("gpt-4o", _settings())
    assert chain[0] == ("openai", "gpt-4o")
    assert len(chain) == len(set(chain))


def test_unknown_requested_model_raises():
    with pytest.raises(UnknownModel):
        resolve_model_chain("totally-made-up", _settings())


def test_unknown_fallback_is_skipped_not_raised():
    """
    Fallbacks are our configuration, not user input. A stale one should not
    take down every otherwise-valid request.
    """
    s = Settings(_env_file=None, fallback_models="gpt-4o,retired-model-v1")
    chain = resolve_model_chain("grok-4", s)
    assert ("openai", "gpt-4o") in chain
    assert not any(m == "retired-model-v1" for _, m in chain)


# ---------- Surfaced at the endpoint ----------


def _submit(client, headers, model):
    return client.post(
        "/v1/analyze/jobs",
        headers=headers,
        json={
            "target": "App",
            "duration_seconds": 10,
            "model": model,
            "frames": [{"index": 0, "image_b64": "AAAA"}],
        },
    )


def test_unknown_model_is_400_at_submit(client, subscribed_user):
    _, headers = subscribed_user
    resp = _submit(client, headers, "gpt4o")
    assert resp.status_code == 400, resp.text
    assert "Unknown model" in resp.json()["detail"]


def test_unknown_model_creates_no_job(client, subscribed_user, portal):
    """Rejected before anything is queued or charged."""
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.jobs import AnalysisJob

    async def _count():
        async with SessionLocal() as s:
            return len((await s.execute(select(AnalysisJob))).scalars().all())

    _, headers = subscribed_user
    before = portal.call(_count)
    assert _submit(client, headers, "not-a-model").status_code == 400
    assert portal.call(_count) == before


def test_known_model_still_accepted(client, subscribed_user):
    _, headers = subscribed_user
    assert _submit(client, headers, "grok-4").status_code == 202


# ---------- Triage shares the map ----------


def test_triage_model_is_validated_against_the_same_registry():
    """
    A misconfigured TRIAGE_MODEL previously went to OpenAI regardless of what
    provider the id belonged to.
    """
    assert provider_for(get_settings().triage_model, _settings()) == "openai"


@pytest.fixture
def portal():
    from anyio.from_thread import start_blocking_portal

    with start_blocking_portal() as p:
        yield p
