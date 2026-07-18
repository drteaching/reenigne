# Deploy reenigne — Supabase + Vercel

## Architecture

```
reenigne.dev          → Vercel (apps/web — Next.js)
api.reenigne.dev      → Vercel (apps/api — FastAPI Python)
Auth + Postgres       → Supabase
```

Provider API keys and Stripe secrets live only on the **API** Vercel project.

---

## 1. Supabase

1. Create a project at [supabase.com](https://supabase.com).
2. **SQL Editor** → paste and run [`supabase/migrations/20260719_profiles.sql`](../supabase/migrations/20260719_profiles.sql).
3. **Authentication → Providers → Email**: enable Email. For smoothest API signup, temporarily disable “Confirm email”.
4. **Settings → API** — copy:
   - Project URL → `SUPABASE_URL`
   - `anon` `public` key → `SUPABASE_ANON_KEY`
   - `service_role` key → `SUPABASE_SERVICE_ROLE_KEY` (API only, never to the browser)
   - JWT Secret → `SUPABASE_JWT_SECRET`
5. **Settings → Database → Connection string → URI** (use **Transaction** pooler on port `6543`):
   - Change `postgresql://` → `postgresql+asyncpg://`
   - Set as `DATABASE_URL` on the API.

---

## 2. Vercel — Marketing site

```bash
cd apps/web
npx vercel login
npx vercel link          # create project e.g. reenigne-web
npx vercel env add NEXT_PUBLIC_API_URL production
# value: https://api.reenigne.dev  (or your API deployment URL)
npx vercel --prod
```

Attach domain `reenigne.dev` in the Vercel project Domain settings.

---

## 3. Vercel — API

```bash
cd apps/api
npx vercel link          # create project e.g. reenigne-api
```

Add these **production** env vars (Vercel dashboard or `vercel env add`):

| Name | Notes |
|------|--------|
| `SUPABASE_URL` | from Supabase |
| `SUPABASE_ANON_KEY` | from Supabase |
| `SUPABASE_SERVICE_ROLE_KEY` | from Supabase |
| `SUPABASE_JWT_SECRET` | from Supabase |
| `DATABASE_URL` | `postgresql+asyncpg://...` pooler URI |
| `XAI_API_KEY` | Grok |
| `OPENAI_API_KEY` | Whisper + fallback |
| `ANTHROPIC_API_KEY` | optional fallback |
| `STRIPE_SECRET_KEY` | optional until billing live |
| `STRIPE_WEBHOOK_SECRET` | |
| `STRIPE_PRICE_ID` | |
| `CORS_ORIGINS` | `https://reenigne.dev,https://www.reenigne.dev` |
| `STRIPE_SUCCESS_URL` | `https://reenigne.dev/account?checkout=success` |
| `STRIPE_CANCEL_URL` | `https://reenigne.dev/pricing?checkout=cancel` |

```bash
npx vercel --prod
```

Attach domain `api.reenigne.dev`.

> Analyze/transcribe need up to **300s** (`vercel.json` `maxDuration`). That requires a Vercel plan that allows it (Pro+). Hobby is capped lower — upgrade or move the API to Fly/Railway if you hit timeouts.

---

## 4. Stripe webhook

Point Stripe to:

`https://api.reenigne.dev/v1/billing/webhook`

---

## 4b. Analysis job runner

`/v1/analyze/jobs` only enqueues. Something must trigger the runner, or jobs
sit in `queued` forever.

Apply the migration:

```bash
supabase db push   # or paste supabase/migrations/20260719_analysis_jobs.sql
```

Then set both of these in Vercel, to the **same** value:

| Var | Why |
|-----|-----|
| `CRON_SECRET` | Vercel sends it as `Authorization: Bearer …` on cron requests |
| `JOB_RUNNER_SECRET` | What the API compares against |

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

`apps/api/vercel.json` already registers the schedule:

```json
"crons": [{ "path": "/v1/internal/jobs/run", "schedule": "* * * * *" }]
```

Verify it works:

```bash
curl -X POST https://api.reenigne.dev/v1/internal/jobs/run \
  -H "X-Job-Runner-Secret: $JOB_RUNNER_SECRET"
# {"processed": 0, "job_ids": []}
```

> **Vercel Cron granularity.** Once per minute on Pro; **once per day** on
> Hobby, which makes the queue unusable there. On Hobby, either point an
> external scheduler at the same endpoint, or run the API on a long-running
> host with `JOB_RUN_INLINE=true`.

Leaving `JOB_RUNNER_SECRET` empty makes the endpoint return 404, so an
unconfigured deploy cannot be drained by anyone who guesses the path.

---

## 5. Desktop / CLI

```bash
export REENIGNE_API_URL=https://api.reenigne.dev
# token from login on the site or:
# POST /v1/auth/login → access_token
export REENIGNE_API_TOKEN=...
```

---

## One-shot script

From repo root (after `vercel login` and Supabase project exist):

```bash
./scripts/deploy-vercel.sh
```

You still must set secrets in the Vercel dashboard the first time.
