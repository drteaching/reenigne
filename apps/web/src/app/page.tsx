import Link from "next/link";
import { ContactStrip, type Frame } from "@/components/ContactStrip";
import { PLAN } from "@/lib/plans";

// The shape a real session takes: frames every few seconds, near-duplicates
// dropped by the perceptual-hash pass before anything is sent for analysis.
const HERO_FRAMES: Frame[] = [
  { n: 1, t: 0 },
  { n: 2, t: 3 },
  { n: 3, t: 6, kept: false },
  { n: 4, t: 9 },
  { n: 5, t: 12 },
  { n: 6, t: 15, kept: false },
  { n: 7, t: 18 },
  { n: 8, t: 21 },
  { n: 9, t: 24, kept: false },
  { n: 10, t: 27 },
];

export default function HomePage() {
  return (
    <>
      <section className="section wrap anim">
        <p className="eyebrow">Competitive teardowns from recorded sessions</p>
        <h1>
          Record a walkthrough.
          <br />
          Get the teardown.
        </h1>
        <p className="lede">
          Talk through a competitor&rsquo;s product while you use it. reenigne captures
          the screen, drops duplicate frames, transcribes your narration against the
          timeline, and returns a structured report — feature inventory with frame
          references, workflow analysis, inferred data model.
        </p>

        <div className="btn-row" style={{ margin: "1.75rem 0 2.5rem" }}>
          <Link href="/download" className="btn primary">
            Download for Mac &amp; Windows
          </Link>
          <Link href="/sample-report" className="btn">
            Read a sample report
          </Link>
        </div>

        <ContactStrip frames={HERO_FRAMES} />
        <p className="mono small muted" style={{ marginTop: "0.6rem" }}>
          10 frames captured · 3 near-duplicates dropped · 7 sent for analysis
        </p>

        <div className="trace-line" aria-hidden="true" />

        <div className="readout hero-readout">
          <p className="readout-label">Feature inventory — excerpt</p>
          <p style={{ marginBottom: "0.5rem" }}>
            <strong style={{ color: "#fff" }}>Availability rules editor</strong> — Settings ›
            Scheduling. Lets an owner express &ldquo;no meetings before 10am on
            Mondays&rdquo; without blocking the whole morning. <span className="cite">[#004, #007]</span>
          </p>
          <p style={{ marginBottom: 0 }}>
            <strong style={{ color: "#fff" }}>Buffer padding</strong> — per event type, not
            global. Implies event types are first-class records, not presets.{" "}
            <span className="cite">[#008]</span>
          </p>
        </div>
        <p className="small muted" style={{ marginTop: "0.75rem" }}>
          From the{" "}
          <Link href="/sample-report">full teardown of Meridian</Link>, a fictional
          scheduling product used to demonstrate the report format.
        </p>
      </section>

      <hr className="sprocket" />

      <section className="section wrap">
        <p className="eyebrow">How it works</p>
        <h2>Three stages, one command</h2>
        <p className="lede">
          The desktop app runs all three. The CLI runs them separately if you want to
          re-analyse a session without recording it again.
        </p>

        <div className="steps">
          <div className="step">
            <span className="step-n">Stage 01 — record</span>
            <h3>Screen and microphone</h3>
            <p>
              ffmpeg captures the display and your narration to a single file. The
              recording stays on your disk and is never uploaded.
            </p>
          </div>
          <div className="step">
            <span className="step-n">Stage 02 — process</span>
            <h3>Frames, transcript, alignment</h3>
            <p>
              A frame every few seconds, near-duplicates dropped by perceptual hash,
              optional OCR, and Whisper transcription aligned to frame timestamps.
            </p>
          </div>
          <div className="step">
            <span className="step-n">Stage 03 — analyse</span>
            <h3>Structured report</h3>
            <p>
              Frames and aligned narration go to a vision model, which returns the
              teardown as Markdown plus a JSON feature matrix. Rendered as a
              self-contained HTML file.
            </p>
          </div>
        </div>
      </section>

      <hr className="sprocket" />

      <section className="section wrap">
        <p className="eyebrow">What comes back</p>
        <h2>A report you can act on</h2>
        <p className="lede">
          Ten sections, every observation tied to the frame it came from, so a claim
          you doubt can be checked against the screenshot that produced it.
        </p>

        <div
          style={{
            display: "grid",
            gap: "1.25rem",
            gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))",
            marginTop: "2rem",
          }}
        >
          {[
            ["Product overview", "Who it targets and what it claims to solve."],
            ["Feature inventory", "Every feature seen, where it lives, which frames show it."],
            ["Workflow analysis", "The primary flow step by step, plus friction points."],
            ["UI/UX patterns", "Design system, component and interaction patterns."],
            ["Inferred data model", "Entities and relationships implied by the interface."],
            ["Opportunities", "Gaps, and what you would do differently."],
          ].map(([title, desc]) => (
            <div key={title} className="panel">
              <h3 style={{ fontSize: "1.05rem", marginBottom: "0.35rem" }}>{title}</h3>
              <p className="small muted" style={{ margin: 0 }}>
                {desc}
              </p>
            </div>
          ))}
        </div>

        <div className="btn-row" style={{ marginTop: "2rem" }}>
          <Link href="/sample-report" className="btn primary">
            Read the full sample report
          </Link>
        </div>
      </section>

      <hr className="sprocket" />

      <section className="section wrap">
        <p className="eyebrow">Who uses it</p>
        <h2>Built for people who have to justify a decision</h2>
        <div
          style={{
            display: "grid",
            gap: "1.5rem",
            gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
            marginTop: "1.5rem",
          }}
        >
          <p className="muted small">
            <strong style={{ color: "var(--graphite)" }}>Product managers</strong> —
            turn a competitor sweep into something you can put in front of a room
            without re-screenshotting everything by hand.
          </p>
          <p className="muted small">
            <strong style={{ color: "var(--graphite)" }}>Founders</strong> — work out
            what an incumbent actually ships before you commit a quarter to matching
            it.
          </p>
          <p className="muted small">
            <strong style={{ color: "var(--graphite)" }}>UX researchers</strong> —
            capture a heuristic walkthrough with the evidence attached to each
            observation.
          </p>
          <p className="muted small">
            <strong style={{ color: "var(--graphite)" }}>Consultants</strong> — hand a
            client a landscape review that cites frames instead of impressions.
          </p>
        </div>
      </section>

      <hr className="sprocket" />

      <section className="section wrap">
        <h2>Start with {PLAN.analysesPerMonth} reports a month</h2>
        <p className="lede">
          Recording and browsing sessions are free. Transcription and analysis run on
          our servers and need a subscription — provider keys never ship inside the
          app.
        </p>
        <div className="btn-row" style={{ marginTop: "1.5rem" }}>
          <Link href="/download" className="btn primary">
            Download
          </Link>
          <Link href="/pricing" className="btn">
            See pricing
          </Link>
        </div>
      </section>
    </>
  );
}
