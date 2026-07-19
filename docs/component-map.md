# Component map

One line per module, naming what it owns. Fed to the feedback triage prompt so
classifications land on real paths — the model is instructed to choose only
from this list and to return an empty list rather than invent one.

Keep it current: a stale map produces confidently wrong routing.

## apps/api — cloud API (FastAPI)

- `app/main.py` — HTTP routes: auth, billing, feedback intake, analysis jobs, webhook.
- `app/auth.py` — JWT verification, Supabase and local dev auth, subscription gate.
- `app/db.py` — engine, session, `profiles` (User) model, uuid helpers.
- `app/config.py` — all settings and the fail-fast startup validation.
- `app/jobs.py` — analysis job queue: enqueue, quota/credit selection, completion, refunds.
- `app/queue.py` — claim/lease/retry mechanics shared by every job queue.
- `app/triage.py` — feedback triage job: prompt assembly, schema validation, sanitisation.
- `app/github.py` — GitHub issue filing for triaged feedback.
- `app/feedback.py` — feedback intake: model, secret scanning, rate limits.
- `app/stripe_billing.py` — Stripe checkout, portal, webhook effects, quota pools.
- `app/llm.py` — provider adapters (Grok, OpenAI, Anthropic) and fallback chain.
- `app/runner_loop.py` — standalone job runner process.
- `reenigne_prompts/` — canonical prompt templates, shared with the worker.

## packages/worker — capture and processing (Python)

- `src/reenigne/cli.py` — `reenigne` command line entry points.
- `src/reenigne/pipeline.py` — record → process → analyze → report orchestration.
- `src/reenigne/capture/` — ffmpeg screen and audio recording, device selection.
- `src/reenigne/process/` — frame extraction, dedupe, OCR, transcript alignment.
- `src/reenigne/analyze/` — cloud analysis client and dev-only local provider path.
- `src/reenigne/render/html.py` — self-contained HTML report generation.
- `src/reenigne/cloud.py` — API client: job submission, polling, frame encoding.
- `src/reenigne/worker_rpc.py` — JSON-RPC bridge used by the desktop app.

## apps/desktop — Electron app

- `electron/main.ts` — main process, worker subprocess, IPC, auto-update.
- `electron/preload.ts` — context bridge exposed to the renderer.
- `src/App.tsx` — UI: record, sessions, account, feedback.

## apps/web — marketing site (Next.js)

- `src/app/` — landing, pricing, download, account, docs, feedback pages.
- `src/lib/plans.ts` — plan numbers mirrored from the API's entitlement defaults.

## Infrastructure

- `supabase/migrations/` — Postgres schema, applied in filename order.
- `.github/workflows/` — CI and the human-triggered Claude investigation.
