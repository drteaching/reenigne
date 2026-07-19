"use client";

import { useState } from "react";
import Link from "next/link";
import { SiteNav } from "@/components/SiteNav";
import { FeedbackForm } from "@/components/FeedbackForm";

const API = process.env.NEXT_PUBLIC_API_URL || "https://api.reenigne.dev";

export default function AccountPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [me, setMe] = useState<{
    email: string;
    subscription_status: string;
    plan: string;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"login" | "register">("login");

  async function auth(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const path = mode === "login" ? "/v1/auth/login" : "/v1/auth/register";
    const res = await fetch(`${API}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json();
    if (!res.ok) {
      setError(data.detail || "Auth failed");
      return;
    }
    setToken(data.access_token);
    localStorage.setItem("reenigne_token", data.access_token);
    const meRes = await fetch(`${API}/v1/me`, {
      headers: { Authorization: `Bearer ${data.access_token}` },
    });
    if (meRes.ok) setMe(await meRes.json());
  }

  async function checkout() {
    if (!token) return;
    const res = await fetch(`${API}/v1/billing/checkout`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    if (res.ok && data.url) window.location.href = data.url;
    else setError(data.detail || "Checkout unavailable — open the desktop app.");
  }

  return (
    <div className="page">
      <SiteNav />
      <section className="section" style={{ maxWidth: 520 }}>
        <h3>Account</h3>
        {me ? (
          <>
            <p>
              Signed in as <strong>{me.email}</strong>
            </p>
            <p style={{ color: "var(--muted)" }}>
              {me.plan} · {me.subscription_status}
            </p>
            <div className="cta-row" style={{ justifyContent: "flex-start", marginTop: 16 }}>
              <button className="btn primary" onClick={checkout}>
                Manage / subscribe
              </button>
              <Link href="/download" className="btn">
                Download app
              </Link>
            </div>
          </>
        ) : (
          <form
            onSubmit={auth}
            style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 16 }}
          >
            <p style={{ color: "var(--muted)" }}>
              Same account works on the web and in the desktop app.
            </p>
            <input
              type="email"
              required
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={{
                padding: 12,
                borderRadius: 10,
                border: "1px solid var(--line)",
                background: "#12171c",
                color: "var(--ink)",
              }}
            />
            <input
              type="password"
              required
              minLength={8}
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={{
                padding: 12,
                borderRadius: 10,
                border: "1px solid var(--line)",
                background: "#12171c",
                color: "var(--ink)",
              }}
            />
            <div className="cta-row" style={{ justifyContent: "flex-start" }}>
              <button className="btn primary" type="submit">
                {mode === "login" ? "Sign in" : "Create account"}
              </button>
              <button
                className="btn"
                type="button"
                onClick={() => setMode((m) => (m === "login" ? "register" : "login"))}
              >
                Switch
              </button>
            </div>
            {error && <p style={{ color: "#ff5c6a" }}>{error}</p>}
          </form>
        )}
      </section>
    </div>
  );
}
