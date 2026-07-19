import Link from "next/link";
import { SiteNav } from "@/components/SiteNav";
import { FeedbackForm } from "@/components/FeedbackForm";

export const metadata = {
  title: "Feedback — reenigne",
  description: "Report a bug or suggest an improvement to reenigne.",
};

export default function FeedbackPage() {
  return (
    <div className="page">
      <SiteNav />
      <section className="section">
        <h3>Feedback</h3>
        <p>
          Found a bug, or want something reenigne doesn’t do yet? Tell us. You
          don’t need an account — reports from this page are anonymous unless
          you’re signed in.
        </p>
        <p className="muted" style={{ fontSize: "0.85rem" }}>
          Every report is read. Recordings, screenshots and transcripts are
          never attached to feedback — only what you type here.
        </p>
        <FeedbackForm />
      </section>
      <footer className="footer">
        <Link href="/">← reenigne</Link>
      </footer>
    </div>
  );
}
