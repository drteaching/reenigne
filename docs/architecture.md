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

**Triggering.** The runner needs something to call it. Vercel Cron is capped
at once per minute (and once per *day* on Hobby), so queue latency is bounded
by whatever schedules it. A long-running host can set `JOB_RUN_INLINE=true`
instead and skip the queue latency entirely.

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
