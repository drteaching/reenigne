"use client";

import { useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "https://api.reenigne.dev";

type Kind = "bug" | "improvement";

/**
 * Feedback form, shared by /feedback and the account page.
 *
 * Submits to the same endpoint the desktop app and CLI use. The API explains
 * its own rejections — a detected secret, a rate limit — in terms the
 * submitter can act on, so those messages are surfaced verbatim rather than
 * replaced with a generic failure.
 */
export function FeedbackForm({ token }: { token?: string | null }) {
  const [kind, setKind] = useState<Kind>("bug");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  // Honeypot. Hidden from people, filled by bots; a filled one is accepted
  // and discarded server-side.
  const [website, setWebsite] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [message, setMessage] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setState("sending");
    setMessage("");
    try {
      const res = await fetch(`${API}/v1/feedback`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ kind, title, description, website }),
      });
      if (res.ok) {
        setState("sent");
        setTitle("");
        setDescription("");
        return;
      }
      const body = await res.json().catch(() => ({}));
      setState("error");
      setMessage(
        typeof body?.detail === "string"
          ? body.detail
          : "Something went wrong. Please try again."
      );
    } catch {
      setState("error");
      setMessage("Could not reach the server. Please try again.");
    }
  }

  if (state === "sent") {
    return (
      <div className="panel">
        <p>
          <strong>Thank you.</strong> Your report was received and will be
          triaged automatically.
        </p>
        <button className="btn" onClick={() => setState("idle")}>
          Send another
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="feedback-form">
      <div className="row" style={{ gap: "0.5rem", marginBottom: "0.75rem" }}>
        {(["bug", "improvement"] as Kind[]).map((k) => (
          <button
            key={k}
            type="button"
            className={kind === k ? "btn primary" : "btn"}
            onClick={() => setKind(k)}
          >
            {k === "bug" ? "Report a bug" : "Suggest an improvement"}
          </button>
        ))}
      </div>

      <label htmlFor="fb-title">Summary</label>
      <input
        id="fb-title"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        maxLength={200}
        required
        placeholder={
          kind === "bug" ? "Recording stops after 30 seconds" : "Export to PDF"
        }
      />

      <label htmlFor="fb-description">Details</label>
      <textarea
        id="fb-description"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        maxLength={5000}
        required
        rows={7}
        placeholder={
          kind === "bug"
            ? "What did you do, what happened, and what did you expect?"
            : "What would you like to be able to do?"
        }
      />
      <p className="muted" style={{ fontSize: "0.8rem" }}>
        {description.length} / 5000 · Please don’t include API keys, tokens or
        passwords — submissions containing them are rejected.
      </p>

      {/* Honeypot: off-screen, not hidden via `display:none`, which some bots
          detect. Real users never focus it. */}
      <div aria-hidden="true" style={{ position: "absolute", left: "-9999px" }}>
        <label htmlFor="website">Website</label>
        <input
          id="website"
          name="website"
          tabIndex={-1}
          autoComplete="off"
          value={website}
          onChange={(e) => setWebsite(e.target.value)}
        />
      </div>

      {state === "error" && (
        <p role="alert" style={{ color: "#ff8080" }}>
          {message}
        </p>
      )}

      <button
        className="btn primary"
        type="submit"
        disabled={state === "sending" || !title.trim() || !description.trim()}
      >
        {state === "sending" ? "Sending…" : "Send"}
      </button>
    </form>
  );
}
