"""Authentication and the subscription gate on paid endpoints."""


def test_health_is_open(client):
    assert client.get("/health").status_code == 200


def test_register_then_login(client):
    creds = {"email": "roundtrip@example.com", "password": "hunter2hunter2"}
    assert client.post("/v1/auth/register", json=creds).status_code == 200
    resp = client.post("/v1/auth/login", json=creds)
    assert resp.status_code == 200
    assert resp.json()["access_token"]


def test_duplicate_registration_rejected(client, user):
    email, _ = user
    resp = client.post(
        "/v1/auth/register", json={"email": email, "password": "hunter2hunter2"}
    )
    assert resp.status_code == 400


def test_short_password_rejected(client):
    resp = client.post(
        "/v1/auth/register", json={"email": "short@example.com", "password": "abc"}
    )
    assert resp.status_code == 422


def test_wrong_password_rejected(client, user):
    email, _ = user
    resp = client.post(
        "/v1/auth/login", json={"email": email, "password": "wrongwrongwrong"}
    )
    assert resp.status_code == 401


def test_me_requires_a_token(client):
    assert client.get("/v1/me").status_code == 401


def test_me_rejects_a_forged_token(client):
    """A token signed with the wrong key must not authenticate."""
    import jwt

    forged = jwt.encode(
        {"sub": "00000000-0000-0000-0000-000000000000", "email": "a@b.test"},
        "not-the-server-signing-key",
        algorithm="HS256",
    )
    resp = client.get("/v1/me", headers={"Authorization": f"Bearer {forged}"})
    assert resp.status_code == 401


def test_me_returns_entitlements(client, user):
    email, headers = user
    body = client.get("/v1/me", headers=headers).json()
    assert body["email"] == email
    assert body["subscription_status"] == "none"
    assert body["minutes_limit"] == 10


def test_paid_endpoints_require_a_subscription(client, user):
    """Unsubscribed users get 402, not access."""
    _, headers = user
    resp = client.post(
        "/v1/analyze",
        headers=headers,
        json={"target": "App", "frames": [], "duration_seconds": 1},
    )
    assert resp.status_code == 402


def test_transcribe_requires_a_subscription(client, user):
    _, headers = user
    resp = client.post(
        "/v1/transcribe",
        headers=headers,
        files={"file": ("a.wav", b"fake-audio", "audio/wav")},
    )
    assert resp.status_code == 402
