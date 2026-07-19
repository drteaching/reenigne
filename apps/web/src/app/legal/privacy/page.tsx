import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Privacy notice (draft)",
  description:
    "What reenigne collects, what leaves your machine, who processes it, and how long it is kept.",
  robots: { index: false, follow: true },
};

export default function PrivacyPage() {
  return (
    <div className="wrap section">
      <p className="eyebrow">Legal</p>
      <h1>Privacy notice</h1>

      <div className="notice">
        <strong>Draft — under review</strong>
        This describes the data flows in the software as built, written so it can be
        checked against the code. It has not yet been reviewed by a lawyer, and the
        operating entity details below are unfilled. Do not treat it as a final legal
        document.
      </div>

      <p className="muted small">Last updated: 19 July 2026</p>

      <h2>Who operates reenigne</h2>
      <p>
        reenigne is operated by <span className="placeholder">[ENTITY NAME — TBC]</span>,
        ABN <span className="placeholder">[ABN — TBC]</span>, based in Australia.
        Enquiries: <span className="placeholder">[CONTACT EMAIL — TBC]</span>.
      </p>

      <h2>What stays on your machine</h2>
      <p>
        The screen recording itself. The <code>recording.mp4</code> for every session
        stays in your local session directory and is never uploaded. The same is true
        of the rendered HTML report and the session manifest.
      </p>

      <h2>What is sent to our servers</h2>
      <ul className="stack" style={{ paddingLeft: "1.2rem", maxWidth: "64ch" }}>
        <li>
          <strong>Audio</strong> extracted from the recording, for transcription.
        </li>
        <li>
          <strong>Selected frames</strong> — the deduplicated set only, downscaled and
          JPEG-encoded before upload. Frames dropped as near-duplicates are never sent.
        </li>
        <li>
          <strong>Your narration transcript</strong> and any OCR text, as part of the
          analysis request.
        </li>
        <li>
          <strong>Account data</strong>: email address, subscription status, and usage
          counters.
        </li>
        <li>
          <strong>Feedback</strong> you submit, plus — only if you tick the boxes —
          your app version, platform, OS, and the last 100 lines of the worker log.
        </li>
      </ul>

      <h2>Third parties who process it</h2>
      <p>We use these categories of processor. Your content passes through them:</p>
      <ul className="stack" style={{ paddingLeft: "1.2rem", maxWidth: "64ch" }}>
        <li>
          <strong>AI model providers</strong> — audio goes to a speech-to-text
          provider; frames and narration go to a vision-capable language model
          provider, with fallback to alternative providers if the first is
          unavailable. Our API keys are held server-side and never shipped in the app.
        </li>
        <li>
          <strong>Payment processing</strong> — Stripe. Card details are entered on
          Stripe&rsquo;s systems and never reach ours. We store a customer identifier
          and subscription status only.
        </li>
        <li>
          <strong>Hosting and database</strong> — our API and Postgres database, and
          the marketing site&rsquo;s host.
        </li>
        <li>
          <strong>Issue tracking</strong> — triaged feedback may be filed as an issue
          in our source repository, with credential patterns and email addresses
          stripped first.
        </li>
      </ul>
      <p className="muted small">
        These providers are located outside Australia, which means your content is
        processed overseas.
      </p>

      <h2>Retention, and what happens if you delete your account</h2>
      <div className="stack" style={{ maxWidth: "64ch" }}>
        <p>
          Analysis jobs discard their frame payload as soon as the job finishes,
          whether it succeeded or failed. The resulting report text is retained on
          your account.
        </p>
        <p>
          <strong>Feedback you submit is retained after account deletion, with your
          identity removed.</strong> Deleting an account sets the feedback&rsquo;s user
          link to null rather than deleting the report. We do this because a feedback
          report may already have become a public issue in our tracker, and deleting
          our copy would orphan that issue rather than erase anything. The text you
          wrote, and any diagnostics you chose to attach, remain — unlinked from you.
        </p>
        <p>
          If you want feedback content itself removed rather than anonymised, ask and
          we will remove it.
        </p>
      </div>

      <h2>Anonymous submissions</h2>
      <p>
        Feedback from the website can be sent without an account. For rate limiting we
        store a keyed hash of the submitting IP address, not the address itself. We
        cannot recover the original address from it.
      </p>

      <h2>Your rights</h2>
      <p>
        Under the Australian Privacy Principles you may request access to the personal
        information we hold about you, ask us to correct it, or complain about how we
        have handled it. Contact{" "}
        <span className="placeholder">[CONTACT EMAIL — TBC]</span>.
      </p>

      <p style={{ marginTop: "2.5rem" }}>
        <Link href="/legal/terms">Terms of use →</Link>
      </p>
    </div>
  );
}
