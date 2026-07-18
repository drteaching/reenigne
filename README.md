# reenigne

> Record once. Reverse-engineer anything.

**reenigne** is a cross-platform desktop product that records screen + narration, auto-captures screenshots, transcribes commentary, and produces a professional reverse-engineering report via cloud AI (Grok primary; OpenAI & Anthropic fallback).

- **Site:** [reenigne.dev](https://reenigne.dev) — marketing, pricing, downloads  
- **Desktop:** Screen Studio–style app for **macOS universal** (Apple Silicon + Intel) and **Windows x64**  
- **Cloud:** Provider API keys stay on the server; features require an active subscription  

## Monorepo

```
apps/
  desktop/     Electron UI
  web/         Next.js marketing site
  api/         FastAPI auth + Stripe + Whisper/LLM proxies
packages/
  worker/      Python capture/process pipeline + CLI
docs/          PRD & architecture
scripts/       Packaging helpers
```

## Quick start (local dev)

### 1. API

```bash
cd apps/api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
# Set XAI_API_KEY, OPENAI_API_KEY (and optionally ANTHROPIC_API_KEY)
uvicorn app.main:app --reload --port 8000
```

The server **refuses to start** if it would be unsafe to serve traffic:

- Supabase Auth unconfigured *and* `API_SECRET_KEY` still the built-in default — JWTs would be forgeable.
- `ENABLE_DEV_ENDPOINTS=true` while Stripe is configured — dev activation would hand out free subscriptions.

For local testing, set `ENABLE_DEV_ENDPOINTS=true` and call `POST /v1/dev/activate` (authenticated) to mark yourself subscribed. It returns 404 whenever the flag is off.

### 2. Worker / CLI

```bash
cd packages/worker
pip install -e ".[dev]"
export REENIGNE_API_URL=http://localhost:8000
export REENIGNE_API_TOKEN=<jwt from /v1/auth/login>
reenigne record --target "Demo"
```

### 3. Desktop

```bash
cd apps/desktop
npm install
export REENIGNE_API_URL=http://localhost:8000
npm run electron:dev
```

### 4. Marketing site

```bash
cd apps/web
npm install
export NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

## Security model

| Secret | Where |
|--------|--------|
| `XAI_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | **API server only** |
| `REENIGNE_API_TOKEN` (JWT) | Desktop keychain / CLI env after login |
| Stripe keys | API server only |

Raw `recording.mp4` stays on the user’s disk. Only audio + selected screenshots go to the API.

Screenshots are downscaled and JPEG-encoded before upload, and the client fits the batch to a payload budget (degrading quality first, dropping frames only as a last resort) so requests stay under the serverless body limit.

## Tests

```bash
npm test              # worker + api
npm run test:worker
npm run test:api
```

## Deploy (Supabase + Vercel)

See **[docs/DEPLOY.md](docs/DEPLOY.md)** for the full checklist.

| Piece | Host |
|-------|------|
| Marketing site | Vercel → `reenigne.dev` (`apps/web`) |
| API | Vercel → `api.reenigne.dev` (`apps/api`) |
| Auth + Postgres | Supabase (`supabase/migrations/`) |

```bash
# After supabase SQL + vercel login + env vars are set:
./scripts/deploy-vercel.sh
```

## Packaging

```bash
./scripts/build-worker.sh          # PyInstaller worker → apps/desktop/resources/worker
./scripts/package-desktop.sh mac   # universal DMG
./scripts/package-desktop.sh win   # NSIS x64
```

Place static ffmpeg binaries in `apps/desktop/resources/ffmpeg/` before shipping. Configure Apple notarization and Windows Authenticode for production releases. Auto-update uses `electron-updater` → GitHub Releases.

## License

MIT
