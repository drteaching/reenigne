"""API settings — provider keys live only here."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Sentinel default. If auth falls back to local JWT while this is still in
# place, anyone can forge a token — startup refuses to boot in that state.
INSECURE_SECRET_KEY = "change-me-in-production-use-long-random-string"

# HS256 signs with SHA-256; a key shorter than the 32-byte hash output
# weakens it (RFC 7518 §3.2).
MIN_SECRET_KEY_BYTES = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "reenigne API"
    # Legacy local JWT (dev only when Supabase unset)
    api_secret_key: str = INSECURE_SECRET_KEY
    access_token_expire_minutes: int = 60 * 24 * 7

    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""
    # Prefer Supabase pooler URI, e.g.
    # postgresql+asyncpg://postgres.[ref]:[password]@aws-0-....pooler.supabase.com:6543/postgres
    database_url: str = "sqlite+aiosqlite:///./reenigne.db"
    # Force NullPool. Required under asyncpg whenever connections may be used
    # from more than one event loop (the test suite), since asyncpg binds a
    # connection to the loop that created it and a pooled reuse from another
    # loop raises "attached to a different loop".
    db_null_pool: bool = False

    # Provider keys — NEVER ship these to clients
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    xai_api_key: str = ""

    # The model allowlist. resolve_model_chain maps id -> provider from these
    # alone; anything else is rejected at submit time rather than guessed at
    # by substring. Changing a model id here is the whole upgrade path.
    grok_model: str = "grok-4"
    openai_model: str = "gpt-4o"
    anthropic_model: str = "claude-sonnet-4-5"
    openai_mini_model: str = "gpt-4o-mini"

    default_model: str = "grok-4"
    fallback_models: str = "gpt-4o,claude-sonnet-4-5"

    # Transcription model. Must be one that returns segment timestamps: the
    # worker aligns narration to frames by segment start/end, so a model
    # without them silently destroys the alignment that makes reports
    # specific. See TRANSCRIPTION_MODELS_WITH_SEGMENTS in app/llm.py.
    transcription_model: str = "whisper-1"

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_id: str = ""
    # One-off credit pack (mode="payment"). Credits are consumed only after
    # the monthly allowance is spent.
    stripe_credit_pack_price_id: str = ""
    credit_pack_size: int = 10
    stripe_success_url: str = "https://reenigne.dev/account?checkout=success"
    stripe_cancel_url: str = "https://reenigne.dev/pricing?checkout=cancel"

    # Entitlements. Analyses are the product unit and the binding constraint;
    # minutes are a secondary abuse guard with deliberately generous headroom,
    # so a normal subscriber never meets them.
    pro_analyses_per_month: int = 30
    pro_minutes_per_month: int = 1000
    pro_max_frames_per_session: int = 60
    max_audio_upload_bytes: int = 100 * 1024 * 1024

    # --- Feedback triage ---
    # Text-only classification call. Cheapest capable model by default: this
    # runs on every submission and reads no images.
    triage_model: str = "gpt-4o-mini"
    # Runway floor for a triage job. Far below the analysis floor because a
    # triage call is one text request measured in seconds, not a vision call
    # measured in minutes — reusing the analysis floor would refuse to start
    # triage with several minutes of budget left.
    triage_min_runway_seconds: int = 60

    # --- GitHub issue filing ---
    # Fine-grained PAT scoped to issues on one repo. The API calls no
    # repo-contents endpoints. Unset means triage still runs and stores its
    # result; nothing is filed and no external call is attempted.
    github_feedback_token: str = ""
    github_feedback_repo: str = ""  # "owner/name"

    # --- Auth rate limiting ---
    # Per address, per minute, per route. Best-effort only: the window is in
    # process memory, so it does not survive a cold start or span instances.
    # See app/ratelimit.py for why that trade was made.
    auth_rate_limit_per_minute: int = 5

    # --- Feedback intake ---
    # Daily caps. Feedback is free and never touches quota or credits, so
    # these are the only thing standing between the endpoint and abuse.
    feedback_max_per_user_per_day: int = 5
    feedback_max_per_ip_per_day: int = 3

    # Opt-in only. Never infer "this is dev" from another key being unset —
    # a missing env var must not hand out free subscriptions.
    enable_dev_endpoints: bool = False

    # --- Analysis job queue ---
    # Shared secret for POST /v1/internal/jobs/run, called by Vercel Cron or
    # an external scheduler. Without it the trigger endpoint is disabled.
    job_runner_secret: str = ""
    # Run the job in-process straight after enqueue. DEV ONLY: the submit
    # request then blocks for the whole analysis. On a long-running host use
    # the standalone runner (python -m app.runner_loop) instead.
    job_run_inline: bool = False
    # How long a runner may hold a job before another may reclaim it. Must
    # exceed the slowest realistic provider call.
    job_lease_seconds: int = 900
    job_max_attempts: int = 3

    # Jobs per runner invocation. One by default: on a platform with a hard
    # execution cap, draining several sequentially makes an overrun near
    # certain, and a killed invocation has already spent provider tokens that
    # the retry spends again. Raise only on a long-running host.
    job_runner_batch_size: int = 1
    # Assumed invocation budget. Keep below the platform's maxDuration so the
    # runner stops itself rather than being killed. Vercel Pro fluid compute
    # allows 800s; 750 leaves margin for startup and commit.
    job_runner_max_seconds: int = 750
    # Runway required before claiming. A job started with less than this is
    # unlikely to finish, so it would burn spend and be retried anyway.
    job_min_runway_seconds: int = 300
    # Idle poll interval for the standalone runner (python -m app.runner_loop).
    job_runner_idle_sleep_seconds: float = 5.0
    # Per-user cap on queued+running jobs, so one account cannot flood it.
    job_max_active_per_user: int = 3

    cors_origins: str = (
        "https://reenigne.dev,https://www.reenigne.dev,"
        "http://localhost:3000,http://localhost:5173"
    )

    @property
    def use_supabase(self) -> bool:
        return bool(self.supabase_url and self.supabase_jwt_secret)

    def validate_runtime(self) -> None:
        """Fail fast on configurations that are unsafe to serve traffic with."""
        if not self.use_supabase:
            if self.api_secret_key == INSECURE_SECRET_KEY:
                raise RuntimeError(
                    "Refusing to start: Supabase Auth is not configured "
                    "(SUPABASE_URL + SUPABASE_JWT_SECRET) and API_SECRET_KEY "
                    "is still the built-in default, so JWTs would be "
                    "forgeable. Set one or the other."
                )
            # RFC 7518 §3.2: an HS256 key shorter than the hash output
            # weakens the signature. PyJWT warns; we refuse.
            if len(self.api_secret_key.encode()) < MIN_SECRET_KEY_BYTES:
                raise RuntimeError(
                    f"Refusing to start: API_SECRET_KEY is too short "
                    f"({len(self.api_secret_key.encode())} bytes, minimum "
                    f"{MIN_SECRET_KEY_BYTES}). Generate one with: "
                    f'python3 -c "import secrets; '
                    f'print(secrets.token_urlsafe(48))"'
                )
        if self.stripe_credit_pack_price_id and not self.stripe_secret_key:
            raise RuntimeError(
                "Refusing to start: STRIPE_CREDIT_PACK_PRICE_ID is set but "
                "STRIPE_SECRET_KEY is not. Credit checkout would fail at the "
                "point of sale, after the user has already committed to buy."
            )
        if self.enable_dev_endpoints and self.stripe_secret_key:
            raise RuntimeError(
                "Refusing to start: ENABLE_DEV_ENDPOINTS is on while Stripe is "
                "configured. /v1/dev/activate would grant free subscriptions."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
