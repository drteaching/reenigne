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
