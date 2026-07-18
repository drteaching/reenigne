# reenigne desktop

Screen Studio–style Electron app for macOS (universal) and Windows x64.

```bash
cd apps/desktop
npm install
# Terminal 1: API running on :8000
export REENIGNE_API_URL=http://localhost:8000
npm run electron:dev
```

## Packaging

```bash
# Bundle Python worker first (from repo root)
./scripts/build-worker.sh

# macOS universal DMG
npm run dist:mac

# Windows x64 installer
npm run dist:win
```

Code signing: set `CSC_LINK` / `CSC_KEY_PASSWORD` (Windows) and Apple notarization env vars for release builds. Auto-update uses `electron-updater` against GitHub Releases.
