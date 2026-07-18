#!/usr/bin/env bash
# Deploy apps/web and apps/api to Vercel (requires: npx vercel login).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Deploying web (reenigne.dev)"
cd "$ROOT/apps/web"
npx vercel pull --yes --environment=production 2>/dev/null || true
npx vercel --prod --yes

echo "==> Deploying API (api.reenigne.dev)"
cd "$ROOT/apps/api"
npx vercel pull --yes --environment=production 2>/dev/null || true
npx vercel --prod --yes

echo "Done. Attach custom domains in the Vercel dashboard if not already linked."
echo "See docs/DEPLOY.md for Supabase SQL + env vars."
