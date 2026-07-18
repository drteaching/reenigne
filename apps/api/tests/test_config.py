"""
Configuration safety.

Both guards exist because the original code inferred "we must be in dev" from
another setting being absent — so a single missing or typo'd env var silently
turned a production deploy into an open one.
"""

import pytest

from app.config import INSECURE_SECRET_KEY, Settings


# Every var Settings reads that these tests care about. Cleared so the result
# reflects the declared defaults, not conftest's test environment or a
# developer's local shell.
_CONFIG_ENV_VARS = [
    "API_SECRET_KEY",
    "ENABLE_DEV_ENDPOINTS",
    "STRIPE_SECRET_KEY",
    "SUPABASE_URL",
    "SUPABASE_JWT_SECRET",
]


@pytest.fixture
def clean_env(monkeypatch):
    for var in _CONFIG_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
        monkeypatch.delenv(var.lower(), raising=False)


def _settings(**kw):
    # _env_file=None so a developer's local .env cannot influence the result.
    return Settings(_env_file=None, **kw)


def test_default_secret_without_supabase_is_refused(clean_env):
    with pytest.raises(RuntimeError, match="forgeable"):
        _settings().validate_runtime()


def test_explicit_secret_without_supabase_is_allowed(clean_env):
    _settings(api_secret_key="a-real-randomly-generated-secret").validate_runtime()


def test_supabase_auth_does_not_need_the_local_secret(clean_env):
    _settings(
        supabase_url="https://project.supabase.co",
        supabase_jwt_secret="jwt-secret",
        api_secret_key=INSECURE_SECRET_KEY,
    ).validate_runtime()


def test_dev_endpoints_with_stripe_configured_is_refused(clean_env):
    with pytest.raises(RuntimeError, match="ENABLE_DEV_ENDPOINTS"):
        _settings(
            api_secret_key="a-sufficiently-long-random-secret-key",
            enable_dev_endpoints=True,
            stripe_secret_key="sk_live_abc123",
        ).validate_runtime()


def test_short_secret_is_refused(clean_env):
    """RFC 7518 wants >=32 bytes for HS256; PyJWT warns, we refuse."""
    with pytest.raises(RuntimeError, match="too short"):
        _settings(api_secret_key="short-key").validate_runtime()


def test_dev_endpoints_default_off(clean_env):
    assert _settings().enable_dev_endpoints is False


# ---------- The live endpoint ----------


def test_dev_activate_grants_subscription_when_enabled(client, user):
    _, headers = user
    assert client.get("/v1/me", headers=headers).json()["subscription_status"] == "none"

    assert client.post("/v1/dev/activate", headers=headers).status_code == 200
    assert (
        client.get("/v1/me", headers=headers).json()["subscription_status"] == "active"
    )


def test_dev_activate_hidden_when_disabled(client, user, settings, monkeypatch):
    """Must 404 — not 403 — so the endpoint's existence isn't advertised."""
    monkeypatch.setattr(settings, "enable_dev_endpoints", False)
    _, headers = user
    assert client.post("/v1/dev/activate", headers=headers).status_code == 404


def test_dev_activate_hidden_when_stripe_configured(
    client, user, settings, monkeypatch
):
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_live_abc123")
    _, headers = user
    assert client.post("/v1/dev/activate", headers=headers).status_code == 404


def test_dev_activate_requires_authentication(client, settings, monkeypatch):
    monkeypatch.setattr(settings, "enable_dev_endpoints", True)
    assert client.post("/v1/dev/activate").status_code == 401
