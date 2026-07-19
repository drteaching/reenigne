"use client";

import { useEffect, useState } from "react";

type Platform = "mac" | "windows" | "unknown";

/**
 * Platform-aware download panel.
 *
 * Binaries are not published yet, so this states that plainly and offers a
 * waitlist rather than a dead link. The waitlist posts to the existing
 * feedback endpoint — no new backend, no new dependency, and the address
 * lands somewhere a person already reads.
 */
export function DownloadPicker() {
  const [platform, setPlatform] = useState<Platform>("unknown");
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [message, setMessage] = useState("");

  useEffect(() => {
    const ua = navigator.userAgent;
    if (/Mac|iPhone|iPad/.test(ua)) setPlatform("mac");
    else if (/Win/.test(ua)) setPlatform("windows");
  }, []);

  async function join(e: React.FormEvent) {
    e.preventDefault();
    setState("sending");
    setMessage("");
    const api = process.env.NEXT_PUBLIC_API_URL || "https://api.reenigne.dev";
    try {
      const res = await fetch(`${api}/v1/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind: "improvement",
          title: "Release waitlist request",
          description: `Please notify ${email} when builds are published. Platform detected: ${platform}.`,
        }),
      });
      if (res.ok) {
        setState("sent");
        return;
      }
      const body = await res.json().catch(() => ({}));
      setState("error");
      setMessage(
        typeof body?.detail === "string" ? body.detail : "Could not sign you up."
      );
    } catch {
      setState("error");
      setMessage("Could not reach the server.");
    }
  }

  const mac = platform === "mac";
  const win = platform === "windows";

  return (
    <div style={{ marginTop: "2rem" }}>
      <div className="notice">
        <strong>Status — pre-release</strong>
        Signed builds are not published yet. The source builds and runs today: see{" "}
        <a href="/docs">the quickstart</a>. Leave an address below and we will write
        once installers are up — nothing else gets sent to it.
      </div>

      <div
        style={{
          display: "grid",
          gap: "1rem",
          gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
        }}
      >
        <div className="panel" style={{ borderWidth: mac ? "2px" : "1px", borderColor: mac ? "var(--graphite)" : "var(--rule)" }}>
          <h2 style={{ fontSize: "1.15rem", marginBottom: "0.25rem" }}>
            macOS{mac && <span className="mono small muted"> · detected</span>}
          </h2>
          <p className="small muted" style={{ marginBottom: "0.75rem" }}>
            Universal build — Apple Silicon and Intel. macOS 12 or later.
          </p>
          <p className="mono small" style={{ margin: 0, color: "var(--signal-ink)" }}>
            .dmg — not yet published
          </p>
        </div>

        <div className="panel" style={{ borderWidth: win ? "2px" : "1px", borderColor: win ? "var(--graphite)" : "var(--rule)" }}>
          <h2 style={{ fontSize: "1.15rem", marginBottom: "0.25rem" }}>
            Windows{win && <span className="mono small muted"> · detected</span>}
          </h2>
          <p className="small muted" style={{ marginBottom: "0.75rem" }}>
            Not available yet. The recorder is built for macOS first, and the
            Windows build needs its own capture path before it is worth shipping.
          </p>
          <p className="mono small" style={{ margin: 0, color: "var(--signal-ink)" }}>
            .exe — no date yet
          </p>
        </div>
      </div>

      <div className="panel" style={{ marginTop: "1.5rem", maxWidth: "34rem" }}>
        {state === "sent" ? (
          <p style={{ margin: 0 }}>
            <strong>Noted.</strong> We will write to that address once installers are
            published.
          </p>
        ) : (
          <form onSubmit={join}>
            <label htmlFor="wl-email">Tell me when it ships</label>
            <input
              id="wl-email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
              autoComplete="email"
            />
            {state === "error" && (
              <p className="form-error" role="alert">
                {message}
              </p>
            )}
            <button
              className="btn primary"
              type="submit"
              disabled={state === "sending" || !email.trim()}
            >
              {state === "sending" ? "Sending…" : "Add me"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
