import type { Metadata } from "next";
import { FeedbackForm } from "@/components/FeedbackForm";

export const metadata: Metadata = {
  title: "Feedback",
  description: "Report a bug or suggest an improvement to reenigne.",
};

export default function FeedbackPage() {
  return (
    <div className="wrap section">
      <p className="eyebrow">Feedback</p>
      <h1>Tell us what broke</h1>
      <p className="lede">
        Or what is missing. You do not need an account — reports from this page are
        anonymous unless you are signed in. Every one is read.
      </p>
      <p className="small muted" style={{ maxWidth: "60ch" }}>
        Recordings, screenshots and transcripts are never attached to feedback; only
        what you type here. Reports are triaged automatically and may become a public
        issue, with credentials and email addresses stripped first.
      </p>
      <div style={{ marginTop: "2rem", maxWidth: "40rem" }}>
        <FeedbackForm />
      </div>
    </div>
  );
}
