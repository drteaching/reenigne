/**
 * Plan numbers shown on the marketing site.
 *
 * These mirror the API's entitlement defaults in apps/api/app/config.py. The
 * site is statically rendered TypeScript and cannot import Python settings, so
 * the numbers are necessarily written twice — apps/api/tests/test_plans_parity.py
 * fails the build if the two drift apart.
 *
 * That parity check compares against the Settings *defaults*, which are the
 * contract this page advertises. If we ever override an entitlement in
 * production, this file stops being trustworthy and the answer is a public
 * GET /v1/plans that the page reads instead.
 *
 * The dollar price is deliberately not here: the real number lives in Stripe,
 * and duplicating it would imply this file is authoritative about billing.
 */

export const PLAN = {
  /** Reports included per month on Pro. */
  analysesPerMonth: 30,
  /** Reports granted by one credit pack purchase. */
  creditPackSize: 10,
  /** Screenshots sent to the model per session. */
  maxFramesPerSession: 60,
} as const;

export const PRO_FEATURES: readonly string[] = [
  `${PLAN.analysesPerMonth} AI teardown reports / month`,
  `Top up any time — ${PLAN.creditPackSize}-report credit packs`,
  "Whisper transcription",
  "Grok teardown (OpenAI + Claude fallback)",
  "Self-contained HTML reports",
  "Mac (Intel + Apple Silicon)",
];
