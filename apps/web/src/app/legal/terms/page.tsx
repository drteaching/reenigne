import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Terms of use (draft)",
  description: "The terms on which reenigne is provided.",
  robots: { index: false, follow: true },
};

export default function TermsPage() {
  return (
    <div className="wrap section">
      <p className="eyebrow">Legal</p>
      <h1>Terms of use</h1>

      <div className="notice">
        <strong>Draft — under review</strong>
        Written to describe the service as actually built. Not yet reviewed by a
        lawyer; entity details below are unfilled. Not a final legal document.
      </div>

      <p className="muted small">Last updated: 19 July 2026</p>

      <h2>Who you are contracting with</h2>
      <p>
        <span className="placeholder">[ENTITY NAME — TBC]</span>, ABN{" "}
        <span className="placeholder">[ABN — TBC]</span>, an Australian entity.
        Australian law governs these terms.
      </p>

      <h2>What you are responsible for</h2>
      <div className="stack" style={{ maxWidth: "64ch" }}>
        <p>
          <strong>What you record.</strong> reenigne records whatever is on your
          screen. Recording another company&rsquo;s software may breach that
          product&rsquo;s terms of service, and recording a screen containing other
          people&rsquo;s personal information carries its own obligations. Both are
          your responsibility, not ours. We do not review what you record.
        </p>
        <p>
          <strong>Your account.</strong> Keep your credentials secure. Activity under
          your account is treated as yours.
        </p>
      </div>

      <h2>What the analysis is, and is not</h2>
      <p>
        Reports are produced by AI models from screenshots and your narration. They
        contain inference and will sometimes be wrong — the report format cites the
        frame behind each observation precisely so you can check it. Do not treat a
        report as verified fact, legal advice, or a substitute for your own judgement.
      </p>

      <h2>Billing</h2>
      <ul className="stack" style={{ paddingLeft: "1.2rem", maxWidth: "64ch" }}>
        <li>Subscriptions are billed monthly through Stripe until cancelled.</li>
        <li>
          A report is charged when it succeeds. Failed analyses are not charged, and a
          credit that paid for a failed report is returned.
        </li>
        <li>
          The monthly allowance resets each month and does not roll over. Purchased
          credits do not expire.
        </li>
        <li>
          Cancel any time from your account; access continues to the end of the paid
          period.
        </li>
      </ul>

      <h2>Acceptable use</h2>
      <p>Do not use reenigne to:</p>
      <ul className="stack" style={{ paddingLeft: "1.2rem", maxWidth: "64ch" }}>
        <li>Record material you have no right to record.</li>
        <li>
          Capture other people&rsquo;s personal or confidential information without a
          lawful basis.
        </li>
        <li>Attempt to extract our prompts, credentials, or model provider keys.</li>
        <li>Resell the service, or submit content designed to attack our systems.</li>
      </ul>

      <h2>Availability</h2>
      <p>
        The service is provided as-is. We do not promise an uptime figure. Analysis
        depends on third-party model providers and can be unavailable when they are.
      </p>

      <h2>Liability</h2>
      <p>
        Nothing here excludes rights you have under the Australian Consumer Law. Beyond
        those, our liability is limited to the amount you paid us in the twelve months
        before the claim.
      </p>

      <h2>Changes</h2>
      <p>
        We may change these terms. Material changes will be notified by email to
        account holders before taking effect.
      </p>

      <p style={{ marginTop: "2.5rem" }}>
        <Link href="/legal/privacy">Privacy notice →</Link>
      </p>
    </div>
  );
}
