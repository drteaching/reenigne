# reenigne API

Cloud backend: Supabase Auth + Postgres, Stripe, Whisper + LLM proxies.
Provider API keys stay on this server only.

**Production:** Vercel (`api.reenigne.dev`) + Supabase — see [docs/DEPLOY.md](../../docs/DEPLOY.md).

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill SUPABASE_* + DATABASE_URL (or leave SQLite for local-only)
uvicorn app.main:app --reload --port 8000
```

## Endpoints

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| POST | `/v1/auth/register` | — | Create account |
| POST | `/v1/auth/login` | — | JWT |
| GET | `/v1/me` | JWT | Entitlements |
| POST | `/v1/billing/checkout` | JWT | Stripe Checkout URL |
| POST | `/v1/billing/portal` | JWT | Customer Portal |
| POST | `/v1/billing/webhook` | Stripe sig | Subscription sync |
| POST | `/v1/transcribe` | JWT + sub | Whisper |
| POST | `/v1/analyze` | JWT + sub | Grok → GPT-4o → Claude |
| POST | `/v1/dev/activate` | JWT | Dev-only activate (no Stripe) |
