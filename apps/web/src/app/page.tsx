import Link from "next/link";
import { SiteNav } from "@/components/SiteNav";

export default function HomePage() {
  return (
    <div className="page">
      <SiteNav />
      <section className="hero">
        <div className="hero-inner">
          <h1 className="brand">reenigne</h1>
          <h2>Record once. Reverse-engineer anything.</h2>
          <p>
            Capture screen + narration while you explore a product. Get a structured AI
            teardown — features, UX, and opportunities — ready to inform your build.
          </p>
          <div className="cta-row">
            <Link href="/download" className="btn primary">
              Download for Mac &amp; Windows
            </Link>
            <Link href="/pricing" className="btn">
              Start free trial
            </Link>
          </div>
        </div>
      </section>

      <section className="section" id="how">
        <h3>How it works</h3>
        <p>One polished desktop app. Local media. Cloud AI only when you subscribe.</p>
        <div className="steps">
          <div className="step">
            <strong>1. Record</strong>
            <span>Walk through any product while narrating. Screen + mic, one click.</span>
          </div>
          <div className="step">
            <strong>2. Process</strong>
            <span>Auto screenshots, Whisper transcription, OCR, time-aligned manifest.</span>
          </div>
          <div className="step">
            <strong>3. Report</strong>
            <span>Grok (with OpenAI/Anthropic fallback) writes a teardown you can ship.</span>
          </div>
        </div>
      </section>

      <section className="section">
        <h3>Built for product people</h3>
        <p>
          Indie founders, PMs, UX researchers, and consultants who need competitor
          intelligence without the spreadsheet grind.
        </p>
      </section>

      <footer className="footer">
        <span>© {new Date().getFullYear()} reenigne · reenigne.dev</span>
        <span>
          <Link href="/legal">Legal</Link> · Recording third-party software may be
          restricted by their ToS — use responsibly.
        </span>
      </footer>
    </div>
  );
}
