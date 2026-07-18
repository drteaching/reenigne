import { useCallback, useEffect, useMemo, useState } from "react";

type Tab = "record" | "sessions" | "account";
type Step = "idle" | "recording" | "process" | "analyze" | "report" | "done" | "error";

type Me = {
  email: string;
  subscription_status: string;
  plan: string;
  minutes_used_month: number;
  minutes_limit: number;
  analyses_used_month: number;
  analyses_limit: number;
};

function formatTimer(seconds: number) {
  const m = Math.floor(seconds / 60)
    .toString()
    .padStart(2, "0");
  const s = Math.floor(seconds % 60)
    .toString()
    .padStart(2, "0");
  return `${m}:${s}`;
}

export default function App() {
  const [tab, setTab] = useState<Tab>("record");
  const [target, setTarget] = useState("");
  const [step, setStep] = useState<Step>("idle");
  const [elapsed, setElapsed] = useState(0);
  const [sessionDir, setSessionDir] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [email, setEmail] = useState<string | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [sessions, setSessions] = useState<{ path: string; name: string }[]>([]);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");

  const subscribed = useMemo(
    () => me?.subscription_status === "active" || me?.subscription_status === "trialing",
    [me]
  );

  const refreshMe = useCallback(async () => {
    if (!window.reenigne) return;
    const auth = await window.reenigne.getAuth();
    setToken(auth.token);
    setEmail(auth.email);
    if (!auth.token) {
      setMe(null);
      return;
    }
    const res = await window.reenigne.apiFetch("/v1/me");
    if (res.status === 200) setMe(res.data as Me);
    else setMe(null);
  }, []);

  useEffect(() => {
    refreshMe();
  }, [refreshMe]);

  useEffect(() => {
    if (step !== "recording") return;
    const t = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(t);
  }, [step]);

  async function loadSessions() {
    try {
      const res = (await window.reenigne.workerRpc("list_sessions")) as {
        sessions: { path: string; name: string }[];
      };
      setSessions(res.sessions || []);
    } catch {
      setSessions([]);
    }
  }

  useEffect(() => {
    if (tab === "sessions") loadSessions();
  }, [tab]);

  async function handleAuth(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const path = authMode === "login" ? "/v1/auth/login" : "/v1/auth/register";
    const res = await window.reenigne.apiFetch(path, "POST", {
      email: authEmail,
      password: authPassword,
    });
    if (res.status >= 400) {
      setError(
        typeof res.data === "object" && res.data && "detail" in (res.data as object)
          ? String((res.data as { detail: string }).detail)
          : "Authentication failed"
      );
      return;
    }
    const data = res.data as { access_token: string };
    await window.reenigne.setAuth(data.access_token, authEmail);
    await refreshMe();
  }

  async function startRecording() {
    setError(null);
    if (!target.trim()) {
      setError("Enter the product name you’re exploring.");
      return;
    }
    if (!token) {
      setTab("account");
      setError("Sign in to continue.");
      return;
    }
    try {
      setElapsed(0);
      setStep("recording");
      const rec = (await window.reenigne.workerRpc("record_start", {
        target: target.trim(),
      })) as { session_dir: string };
      setSessionDir(rec.session_dir);
    } catch (err) {
      setStep("error");
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function stopAndPipeline() {
    if (!sessionDir) return;
    if (!subscribed) {
      setError("An active subscription is required for processing and AI analysis.");
      try {
        await window.reenigne.workerRpc("record_stop", { session_dir: sessionDir });
      } catch {
        /* ignore */
      }
      setStep("idle");
      return;
    }
    setError(null);
    try {
      await window.reenigne.workerRpc("record_stop", { session_dir: sessionDir });

      setStep("process");
      await window.reenigne.workerRpc("process", {
        session_dir: sessionDir,
      });

      setStep("analyze");
      await window.reenigne.workerRpc("analyze", {
        session_dir: sessionDir,
        prompt: "teardown",
        model: "grok-4",
      });

      setStep("report");
      const report = (await window.reenigne.workerRpc("report", {
        session_dir: sessionDir,
        format: "html",
      })) as { path: string };

      setStep("done");
      await window.reenigne.openPath(report.path);
      await refreshMe();
    } catch (err) {
      setStep("error");
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function checkout() {
    const res = await window.reenigne.apiFetch("/v1/billing/checkout", "POST");
    if (res.status === 200 && res.data && typeof res.data === "object") {
      const url = (res.data as { url: string }).url;
      await window.reenigne.openExternal(url);
    } else {
      // Dev fallback
      const act = await window.reenigne.apiFetch("/v1/dev/activate", "POST");
      if (act.status === 200) await refreshMe();
      else setError("Could not start checkout. Configure Stripe or use /v1/dev/activate.");
    }
  }

  return (
    <div className="app">
      <div className="drag" />
      <div className="shell">
        <nav className="nav">
          <div className="brand">reenigne</div>
          <button className={tab === "record" ? "active" : ""} onClick={() => setTab("record")}>
            Record
          </button>
          <button
            className={tab === "sessions" ? "active" : ""}
            onClick={() => setTab("sessions")}
          >
            Sessions
          </button>
          <button className={tab === "account" ? "active" : ""} onClick={() => setTab("account")}>
            Account
          </button>
          <div style={{ flex: 1 }} />
          {subscribed ? (
            <span className="badge">Pro · active</span>
          ) : (
            <span className="badge warn">Subscription required</span>
          )}
        </nav>

        <main className="main">
          {tab === "record" && (
            <>
              {!subscribed && token && (
                <div className="lock-banner">
                  Cloud transcription and AI analysis unlock with an active subscription.{" "}
                  <button className="btn primary" onClick={checkout}>
                    Upgrade
                  </button>
                </div>
              )}

              <div className="hero-record">
                <h1>Record once. Reverse-engineer anything.</h1>
                <p>
                  Capture screen + narration while you explore a product. reenigne builds a
                  structured teardown report with Grok.
                </p>
                <input
                  className="target-input"
                  placeholder="Product name (e.g. Heidi Health)"
                  value={target}
                  onChange={(e) => setTarget(e.target.value)}
                  disabled={step === "recording" || step === "process"}
                />
                <button
                  className={`record-btn ${step === "recording" ? "recording" : ""}`}
                  onClick={() => {
                    if (step === "recording") void stopAndPipeline();
                    else if (step === "idle" || step === "done" || step === "error")
                      void startRecording();
                  }}
                  disabled={
                    !token ||
                    (!target.trim() && step !== "recording") ||
                    ["process", "analyze", "report"].includes(step)
                  }
                  aria-label={step === "recording" ? "Stop recording" : "Start recording"}
                  title={!token ? "Sign in first" : step === "recording" ? "Stop" : "Record"}
                />
                <div className="timer">{formatTimer(elapsed)}</div>
                {step !== "idle" && (
                  <div className="progress" style={{ width: "min(480px, 100%)" }}>
                    {(
                      [
                        ["recording", "Capture screen + mic"],
                        ["process", "Frames · Whisper · OCR"],
                        ["analyze", "Grok teardown"],
                        ["report", "HTML report"],
                      ] as const
                    ).map(([key, label]) => {
                      const order = ["recording", "process", "analyze", "report", "done"];
                      const cur = order.indexOf(step === "error" ? "recording" : step);
                      const idx = order.indexOf(key);
                      const cls =
                        step === "done" || idx < cur
                          ? "step done"
                          : idx === cur
                            ? "step active"
                            : "step";
                      return (
                        <div key={key} className={cls}>
                          <span>{label}</span>
                          <span className="muted">
                            {step === "done" || idx < cur
                              ? "done"
                              : idx === cur
                                ? "…"
                                : ""}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}
                {sessionDir && <p className="muted">Session: {sessionDir}</p>}
                {error && <p className="error">{error}</p>}
                <div className="row">
                  <button className="btn ghost" onClick={() => window.reenigne.showPermissionsHelp()}>
                    Permissions help
                  </button>
                </div>
              </div>
            </>
          )}

          {tab === "sessions" && (
            <div className="panel">
              <h2>Session library</h2>
              <p className="muted">Local recordings in ~/reenigne — portable and inspectable.</p>
              <ul className="list">
                {sessions.map((s) => (
                  <li key={s.path}>
                    <span>{s.name}</span>
                    <button className="btn" onClick={() => window.reenigne.openPath(s.path)}>
                      Open folder
                    </button>
                  </li>
                ))}
                {sessions.length === 0 && <li className="muted">No sessions yet.</li>}
              </ul>
            </div>
          )}

          {tab === "account" && (
            <div className="panel">
              <h2>Account</h2>
              {token && me ? (
                <>
                  <p>
                    Signed in as <strong>{me.email || email}</strong>
                  </p>
                  <p className="muted">
                    Plan: {me.plan} · {me.subscription_status}
                  </p>
                  <p className="muted">
                    This month: {me.analyses_used_month} / {me.analyses_limit} analyses ·{" "}
                    {me.minutes_used_month.toFixed(1)} / {me.minutes_limit} min
                  </p>
                  <div className="row" style={{ marginTop: 16 }}>
                    {!subscribed && (
                      <button className="btn primary" onClick={checkout}>
                        Start subscription
                      </button>
                    )}
                    {subscribed && (
                      <button
                        className="btn"
                        onClick={async () => {
                          const res = await window.reenigne.apiFetch(
                            "/v1/billing/portal",
                            "POST"
                          );
                          if (res.status === 200) {
                            await window.reenigne.openExternal(
                              (res.data as { url: string }).url
                            );
                          }
                        }}
                      >
                        Manage billing
                      </button>
                    )}
                    <button
                      className="btn ghost"
                      onClick={async () => {
                        await window.reenigne.clearAuth();
                        await refreshMe();
                      }}
                    >
                      Sign out
                    </button>
                  </div>
                </>
              ) : (
                <form className="auth-form" onSubmit={handleAuth}>
                  <p className="muted">
                    Sign in to unlock cloud Whisper + Grok analysis. API keys never ship in the
                    app.
                  </p>
                  <input
                    type="email"
                    placeholder="Email"
                    value={authEmail}
                    onChange={(e) => setAuthEmail(e.target.value)}
                    required
                  />
                  <input
                    type="password"
                    placeholder="Password"
                    value={authPassword}
                    onChange={(e) => setAuthPassword(e.target.value)}
                    required
                    minLength={8}
                  />
                  <div className="row">
                    <button className="btn primary" type="submit">
                      {authMode === "login" ? "Sign in" : "Create account"}
                    </button>
                    <button
                      className="btn ghost"
                      type="button"
                      onClick={() =>
                        setAuthMode((m) => (m === "login" ? "register" : "login"))
                      }
                    >
                      {authMode === "login" ? "Need an account?" : "Have an account?"}
                    </button>
                  </div>
                  {error && <p className="error">{error}</p>}
                </form>
              )}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
