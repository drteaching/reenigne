# reenigne — Architecture

## High-level

```
Desktop (Electron) ──JSON-RPC──► Python worker (local ffmpeg/OCR)
       │                              │
       │ JWT                          │ audio + frames
       ▼                              ▼
Marketing site (reenigne.dev)     Cloud API (FastAPI)
       │                              │
       └──────── Stripe ◄─────────────┤
                                      ├── Whisper (OpenAI key)
                                      └── Grok → GPT-4o → Claude
```

## Analysis jobs

Vision analysis takes minutes — longer than a serverless function may run,
and longer than a client should hold a connection open. So `/v1/analyze/jobs`
enqueues and returns `202` immediately; execution happens out of band.

```
client ──POST /v1/analyze/jobs──► 202 {job_id}     (quota debited here)
   │                                   │
   │                                   ▼
   │                          analysis_jobs (Postgres)
   │                                   ▲
   │                                   │ claim → run → complete
   │                       ┌───────────┴───────────┐
   │                       │ runner trigger        │
   │                       │ • Vercel Cron (1/min) │
   │                       │ • external scheduler  │
   │                       │ • inline (dev/VM)     │
   │                       └───────────────────────┘
   └──GET /v1/analyze/jobs/{id}──► queued | running | succeeded | failed
```

**Claiming.** Runners take the oldest runnable job via a conditional
`UPDATE ... WHERE status='queued' OR lease expired`. Deliberately not
`FOR UPDATE SKIP LOCKED`, so the identical path runs on SQLite locally. Two
runners may read the same candidate; only one matches the predicate on write.

**Leases.** A claim sets `lease_expires_at`. If a runner dies mid-flight, the
job becomes reclaimable once the lease lapses, rather than stranding forever.

**Retries and billing.** Quota is debited at enqueue so queued work counts
against the limit. A job retries up to `JOB_MAX_ATTEMPTS`; on terminal failure
the debit is refunded, since the work never happened. Terminal jobs drop their
frames payload — by far the largest column, and useless afterwards.

**Metering.** Two allowances per month: minutes and analyses. Minutes are
debited at enqueue and refunded if the job ultimately fails, so the refund is
guarded by the usage period it was debited in. The analysis credit is charged
only when a job succeeds — a user is never billed for a report they did not
receive, and there is nothing to refund. Because nothing is reserved, the
enqueue check counts jobs already in flight toward the allowance; otherwise
several concurrent submissions would each pass the check and overshoot.

Quota checks, the minutes debit and the insert all run in one transaction
holding `SELECT ... FOR UPDATE` on the user row, which serialises submissions
per user — the scope of every limit involved. SQLite has no row locks, so the
dev backend is best-effort; `make test-api-pg` covers the real behaviour.

**Triggering.** The runner needs something to call it. Vercel Cron is capped
at once per minute (and once per *day* on Hobby), so queue latency is bounded
by whatever schedules it. A long-running host can set `JOB_RUN_INLINE=true`
instead and skip the queue latency entirely.

## Prompt templates

The prompts are the product, so the paid server path and the worker's local
dev path must never resolve different text for the same template name. There
is exactly one definition: `apps/api/reenigne_prompts/`, a zero-dependency
package that both consumers import.

It lives under `apps/api` because that is the Vercel deployment root —
`scripts/deploy-vercel.sh` runs `vercel` from inside `apps/api`, so nothing
outside that directory is uploaded. A shared package at `packages/` would have
been unreachable at runtime without changing how the API deploys. Keeping the
canonical copy inside the deployment root means the server imports it with no
packaging step, no `requirements.txt` entry and no build hook.

The worker installs the same directory as a real distribution
(`pip install -e ../../apps/api`), which is why `apps/api/pyproject.toml`
exists. That file packages *only* `reenigne_prompts` — never `app`, `api` or
`tests` — and is listed in `.vercelignore` so it cannot influence the Vercel
build, which still installs from `requirements.txt`.

Enforcement, so the duplication cannot return:

| Check | Where |
|-------|-------|
| Exactly one module defines `PROMPTS` | `apps/api/tests/test_prompt_single_source.py` |
| Both consumers import from `reenigne_prompts` | same file (AST check) |
| Each consumer resolves the *same object* | both suites — identity, so text cannot diverge |
| Package stays dependency-free | both suites |

## Packages

| Path | Role |
|------|------|
| `apps/desktop` | Screen Studio–like UI, tray, subscription gate |
| `apps/web` | Landing, pricing, download, account |
| `apps/api` | Auth, Stripe webhooks, AI proxies |
| `packages/worker` | Capture / process / report + CLI `reenigne` |

## Secrets

Provider API keys exist **only** in `apps/api` environment. Desktop builds ship without them.

## Platforms

- macOS universal (arm64 + x86_64) via electron-builder `--universal`
- Windows x64 NSIS
- Bundled ffmpeg under `extraResources`

## LLM routing

1. Requested model (default `grok-4` via xAI)
2. Fallback `gpt-4o`
3. Fallback `claude-sonnet-4-5`
