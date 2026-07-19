"use client";

import { useState } from "react";
import Link from "next/link";
import { FeedbackForm } from "@/components/FeedbackForm";
import { PLAN } from "@/lib/plans";

const API = process.env.NEXT_PUBLIC_API_URL || "https://api.reenigne.dev";

type Me = {
  email: string;
  subscription_status: string;
  plan: string;
  minutes_used_month: number;
  minutes_limit: number;
  analyses_used_month: number;
  analyses_limit: number;
  credits: number;
};

export default function AccountPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"login" | "register">("login");
  const [busy, setBusy] = useState(false);

  async function loadMe(t: string) {
    const res = await fetch(`${API}/v1/me`, {
      headers: { Authorization: `Bearer ${t}` },
    });
    if (res.ok) setMe(await res.json());
  }

  async function auth(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const path = mode === "login" ? "/v1/auth/login" : "/v1/auth/register";
      const res = await fetch(`${API}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(typeof body?.detail === "string" ? body.detail : "Sign-in failed.");
        return;
      }
      setToken(body.access_token);
      await loadMe(body.access_token);
    } catch {
      setError("Could not reach the server.");
    } finally {
      setBusy(false);
    }
  }

  async function startCheckout(path: string) {
    if (!token) return;
    const res = await fetch(`${API}${path}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    const body = await res.json().catch(() => ({}));
    if (res.ok && body?.url) {
      window.location.href = body.url;
      return;
    }
    setError(
      typeof body?.detail === "string" ? body.detail : "Could not start checkout."
    );
  }

  const subscribed =
    me?.subscription_status === "active" || me?.subscription_status === "trialing";

  return (
    <div className="wrap section">
      <p className="eyebrow">Account</p>

      {!me ? (
        <>
          <h1>{mode === "login" ? "Sign in" : "Create an account"}</h1>
          <p className="lede">
            An account is needed for transcription and analysis. Recording and
            browsing sessions work without one.
          </p>

          <form onSubmit={auth} className="panel" style={{ maxWidth: "26rem", marginTop: "2rem" }}>
            <label htmlFor="ac-email">Email</label>
            <input
              id="ac-email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />

            <label htmlFor="ac-password">Password</label>
            <input
              id="ac-password"
              type="password"
              required
              minLength={8}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <p className="field-note">At least 8 characters.</p>

            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}

            <div className="btn-row">
              <button className="btn primary" type="submit" disabled={busy}>
                {busy ? "Working…" : mode === "login" ? "Sign in" : "Create account"}
              </button>
              <button
                type="button"
                className="btn"
                onClick={() => {
                  setMode(mode === "login" ? "register" : "login");
                  setError(null);
                }}
              >
                {mode === "login" ? "Need an account?" : "Have an account?"}
              </button>
            </div>
          </form>
        </>
      ) : (
        <>
          <h1>Your account</h1>
          <p className="mono muted">{me.email}</p>

          <div
            style={{
              display: "grid",
              gap: "1rem",
              gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
              marginTop: "2rem",
            }}
          >
            <div className="panel">
              <p className="eyebrow" style={{ marginBottom: "0.5rem" }}>
                Plan
              </p>
              <p className="mono" style={{ margin: 0, fontSize: "1.1rem" }}>
                {me.plan} · {me.subscription_status}
              </p>
            </div>
            <div className="panel">
              <p className="eyebrow" style={{ marginBottom: "0.5rem" }}>
                Reports this month
              </p>
              <p className="mono" style={{ margin: 0, fontSize: "1.1rem" }}>
                {me.analyses_used_month} / {me.analyses_limit}
              </p>
            </div>
            <div className="panel">
              <p className="eyebrow" style={{ marginBottom: "0.5rem" }}>
                Credits
              </p>
              <p className="mono" style={{ margin: 0, fontSize: "1.1rem" }}>
                {me.credits}
              </p>
            </div>
          </div>

          <p className="small muted" style={{ marginTop: "1rem" }}>
            Processing minutes used: {me.minutes_used_month.toFixed(0)} /{" "}
            {me.minutes_limit}. This is an abuse ceiling, not the limit you will meet
            in normal use.
          </p>

          {error && (
            <p className="form-error" role="alert" style={{ marginTop: "1rem" }}>
              {error}
            </p>
          )}

          <div className="btn-row" style={{ marginTop: "1.5rem" }}>
            {!subscribed && (
              <button className="btn primary" onClick={() => startCheckout("/v1/billing/checkout")}>
                Start subscription
              </button>
            )}
            {subscribed && (
              <>
                <button
                  className="btn primary"
                  onClick={() => startCheckout("/v1/billing/checkout-credits")}
                >
                  Buy {PLAN.creditPackSize} credits
                </button>
                <button className="btn" onClick={() => startCheckout("/v1/billing/portal")}>
                  Manage billing
                </button>
              </>
            )}
          </div>
        </>
      )}

      <hr className="sprocket" style={{ margin: "3rem 0 2rem" }} />

      <h2>Send feedback</h2>
      <p className="muted" style={{ maxWidth: "60ch" }}>
        Report a bug or suggest an improvement. Recordings and transcripts are never
        attached — only what you type.
      </p>
      <div style={{ maxWidth: "40rem", marginTop: "1.5rem" }}>
        <FeedbackForm token={token} />
      </div>

      <p className="small muted" style={{ marginTop: "2.5rem" }}>
        <Link href="/legal/privacy">Privacy notice</Link> ·{" "}
        <Link href="/legal/terms">Terms</Link>
      </p>
    </div>
  );
}
