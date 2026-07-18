"""Client-side job submission and polling."""

import json

import pytest

from reenigne import cloud as cloud_module
from reenigne.cloud import CloudAPIError, CloudClient

ME_ACTIVE = {"subscription_status": "active", "plan": "pro"}


class _Response:
    """Minimal stand-in for httpx.Response covering what CloudClient reads."""

    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.reason_phrase = ""

    @property
    def text(self):
        return json.dumps(self._payload)

    def json(self):
        return self._payload


@pytest.fixture
def fake_http(monkeypatch):
    """
    Script the API. `calls` records every request; `queue` maps a URL suffix
    to a list of responses consumed in order (the last one repeats).
    """
    state = {"calls": [], "routes": {}}

    class _Client:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def _handle(self, method, url, **kw):
            state["calls"].append((method, url))
            # Longest match wins, so "/v1/analyze/jobs" cannot shadow
            # "/v1/analyze/jobs/{id}" depending on dict order.
            matches = [s for s in state["routes"] if s in url]
            if not matches:
                raise AssertionError(f"unrouted request: {method} {url}")
            responses = state["routes"][max(matches, key=len)]
            return responses.pop(0) if len(responses) > 1 else responses[0]

        def get(self, url, **kw):
            return self._handle("GET", url, **kw)

        def post(self, url, **kw):
            return self._handle("POST", url, **kw)

    monkeypatch.setattr(cloud_module.httpx, "Client", _Client)
    monkeypatch.setattr(cloud_module.time, "sleep", lambda s: None)
    return state


def _client():
    return CloudClient("https://api.example.com", "token-123")


def test_submit_returns_job_id(fake_http):
    fake_http["routes"] = {
        "/v1/me": [_Response(200, ME_ACTIVE)],
        "/v1/analyze/jobs": [_Response(202, {"job_id": "job-1", "status": "queued"})],
    }
    job_id = _client().submit_analysis(
        target="App",
        duration_seconds=60,
        prompt_template="teardown",
        model="grok-4",
        frames=[{"index": 1, "image_b64": "AAAA"}],
    )
    assert job_id == "job-1"


def test_polls_until_succeeded(fake_http):
    fake_http["routes"] = {
        "/v1/analyze/jobs/job-1": [
            _Response(200, {"status": "queued"}),
            _Response(200, {"status": "running"}),
            _Response(
                200,
                {
                    "status": "succeeded",
                    "markdown": "# Teardown",
                    "features": {"a": 1},
                },
            ),
        ]
    }
    markdown, features = _client().wait_for_analysis("job-1", poll_interval=0)
    assert markdown == "# Teardown"
    assert features == {"a": 1}


def test_progress_callback_fires_once_per_status_change(fake_http):
    fake_http["routes"] = {
        "/v1/analyze/jobs/job-1": [
            _Response(200, {"status": "queued"}),
            _Response(200, {"status": "queued"}),
            _Response(200, {"status": "running"}),
            _Response(200, {"status": "succeeded", "markdown": "x", "features": {}}),
        ]
    }
    seen = []
    _client().wait_for_analysis(
        "job-1", poll_interval=0, on_progress=lambda s, j: seen.append(s)
    )
    assert seen == ["queued", "running", "succeeded"]


def test_failed_job_raises_with_the_server_error(fake_http):
    fake_http["routes"] = {
        "/v1/analyze/jobs/job-1": [
            _Response(200, {"status": "failed", "error": "all providers failed"})
        ]
    }
    with pytest.raises(CloudAPIError, match="all providers failed"):
        _client().wait_for_analysis("job-1", poll_interval=0)


def test_timeout_mentions_the_job_is_still_running(fake_http):
    """The work continues server-side; the id must stay actionable."""
    fake_http["routes"] = {
        "/v1/analyze/jobs/job-1": [_Response(200, {"status": "running"})]
    }
    with pytest.raises(CloudAPIError) as exc:
        _client().wait_for_analysis("job-1", poll_interval=0, max_wait_seconds=0)
    assert "still running" in str(exc.value)
    assert "job-1" in str(exc.value)


def test_missing_job_raises_404(fake_http):
    fake_http["routes"] = {
        "/v1/analyze/jobs/nope": [_Response(404, {"detail": "Job not found"})]
    }
    with pytest.raises(CloudAPIError) as exc:
        _client().get_analysis_job("nope")
    assert exc.value.status_code == 404


def test_active_job_cap_surfaces_the_server_message(fake_http):
    fake_http["routes"] = {
        "/v1/me": [_Response(200, ME_ACTIVE)],
        "/v1/analyze/jobs": [
            _Response(429, {"detail": "You already have 3 analyses in progress"})
        ],
    }
    with pytest.raises(CloudAPIError) as exc:
        _client().submit_analysis(
            target="App",
            duration_seconds=1,
            prompt_template="teardown",
            model="grok-4",
            frames=[{"index": 1, "image_b64": "A"}],
        )
    assert exc.value.status_code == 429
    assert "3 analyses in progress" in str(exc.value)


def test_unsubscribed_user_is_rejected_before_upload(fake_http):
    """Don't spend bandwidth uploading frames we know will be refused."""
    fake_http["routes"] = {"/v1/me": [_Response(200, {"subscription_status": "none"})]}
    with pytest.raises(CloudAPIError) as exc:
        _client().submit_analysis(
            target="App",
            duration_seconds=1,
            prompt_template="teardown",
            model="grok-4",
            frames=[{"index": 1, "image_b64": "A"}],
        )
    assert exc.value.status_code == 402
    assert not any("/v1/analyze" in url for _, url in fake_http["calls"])


def test_analyze_submits_then_polls(fake_http):
    fake_http["routes"] = {
        "/v1/me": [_Response(200, ME_ACTIVE)],
        "/v1/analyze/jobs/job-9": [
            _Response(200, {"status": "succeeded", "markdown": "# R", "features": {}})
        ],
        "/v1/analyze/jobs": [_Response(202, {"job_id": "job-9", "status": "queued"})],
    }
    markdown, _ = _client().analyze(
        target="App",
        duration_seconds=60,
        prompt_template="teardown",
        model="grok-4",
        frames=[{"index": 1, "image_b64": "A"}],
    )
    assert markdown == "# R"
