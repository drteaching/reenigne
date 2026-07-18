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

    # Provider keys — NEVER ship these to clients
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    xai_api_key: str = ""

    default_model: str = "grok-4"
    fallback_models: str = "gpt-4o,claude-sonnet-4-5"

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_id: str = ""
    stripe_success_url: str = "https://reenigne.dev/account?checkout=success"
    stripe_cancel_url: str = "https://reenigne.dev/pricing?checkout=cancel"

    # Entitlements
    pro_minutes_per_month: int = 300
    pro_max_frames_per_session: int = 60
    max_audio_upload_bytes: int = 100 * 1024 * 1024

    # Opt-in only. Never infer "this is dev" from another key being unset —
    # a missing env var must not hand out free subscriptions.
    enable_dev_endpoints: bool = False

    # --- Analysis job queue ---
    # Shared secret for POST /v1/internal/jobs/run, called by Vercel Cron or
    # an external scheduler. Without it the trigger endpoint is disabled.
    job_runner_secret: str = ""
    # Run the job in-process straight after enqueue. Correct for local dev and
    # long-running hosts; useless on serverless, where the process is frozen
    # once the response is sent.
    job_run_inline: bool = False
    # How long a runner may hold a job before another may reclaim it. Must
    # exceed the slowest realistic provider call.
    job_lease_seconds: int = 900
    job_max_attempts: int = 3
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
        if self.enable_dev_endpoints and self.stripe_secret_key:
            raise RuntimeError(
                "Refusing to start: ENABLE_DEV_ENDPOINTS is on while Stripe is "
                "configured. /v1/dev/activate would grant free subscriptions."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
