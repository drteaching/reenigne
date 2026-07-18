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

`/v1/analyze/jobs` only enqueues. Something must execute the queue, or jobs
sit in `queued` forever.

Apply the migration first:

```bash
supabase db push   # or paste supabase/migrations/*.sql in filename order
```

Pick **one** of three tiers.

### Tier 1 — Local development: inline

```bash
JOB_RUN_INLINE=true
```

The submit request runs the analysis in-process and returns only when it
finishes, so it blocks for **the full duration — minutes**. No runner process
to manage, which is the entire point. Never use this where requests time out.

### Tier 2 — Vercel: cron trigger

Requires **Vercel Pro**. `apps/api/vercel.json` sets `maxDuration: 800`, the
fluid-compute maximum; Hobby caps at 300s and its cron fires only **once per
day**, which makes the queue unusable there.

Set both of these to the **same** value:

| Var | Why |
|-----|-----|
| `CRON_SECRET` | Vercel sends it as `Authorization: Bearer …` on cron requests |
| `JOB_RUNNER_SECRET` | What the API compares against |

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

The schedule is already registered:

```json
"crons": [{ "path": "/v1/internal/jobs/run", "schedule": "* * * * *" }]
```

Verify:

```bash
curl -X POST https://api.reenigne.dev/v1/internal/jobs/run \
  -H "X-Job-Runner-Secret: $JOB_RUNNER_SECRET"
# {"processed":0,"job_ids":[],"stopped":"queue_empty","runway_seconds":749.9}
```

Caveats you are accepting:

- **One job per invocation** (`JOB_RUNNER_BATCH_SIZE=1`). Draining several
  sequentially inside a capped invocation risks being killed mid-call.
- **Up to a minute of queue latency**, since cron fires at most once a minute.
- The runner refuses to claim a job with less than `JOB_MIN_RUNWAY_SECONDS`
  (default 300) left, so an analysis slower than ~450s can never complete
  here. It will retry forever and burn spend each time.

### Tier 3 — Recommended: standalone runner

Run the API anywhere, and the runner as a second long-running process with
the same environment:

```bash
python -m app.runner_loop
```

No invocation ceiling, so a provider call cannot be killed part-way through,
and no queue latency — it picks work up as soon as it lands. On Fly or
Railway this is a second process in the same app:

```toml
# fly.toml
[processes]
  api    = "uvicorn app.main:app --host 0.0.0.0 --port 8080"
  runner = "python -m app.runner_loop"
```

It needs `DATABASE_URL` and the provider keys; it serves no HTTP. Leave
`JOB_RUN_INLINE` unset and `JOB_RUNNER_SECRET` empty (which makes the trigger
endpoint 404, so an unconfigured deploy cannot be drained by path-guessing).
Scale to several runners if needed — claims are atomic, so they will not
double-serve a job.

### Runner settings

| Var | Default | Meaning |
|-----|---------|---------|
| `JOB_RUNNER_BATCH_SIZE` | `1` | Jobs per invocation. Raise only on tier 3. |
| `JOB_RUNNER_MAX_SECONDS` | `750` | Assumed invocation budget. Keep under the platform `maxDuration`. |
| `JOB_MIN_RUNWAY_SECONDS` | `300` | Refuse to claim with less runway than this. |
| `JOB_LEASE_SECONDS` | `900` | Before a stalled job is reclaimable. Must exceed the slowest provider call. |
| `JOB_MAX_ATTEMPTS` | `3` | Then the job fails terminally and its quota is refunded. |
| `JOB_RUNNER_IDLE_SLEEP_SECONDS` | `5` | Tier 3 poll interval when the queue is empty. |

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
