import type { Metadata } from "next";
import Link from "next/link";
import { PLAN, PRO_FEATURES } from "@/lib/plans";

export const metadata: Metadata = {
  title: "Pricing",
  description: `Pro includes ${PLAN.analysesPerMonth} teardown reports a month. Top up with ${PLAN.creditPackSize}-report credit packs. Recording and browsing sessions are free.`,
  openGraph: {
    title: "Pricing — reenigne",
    description: `${PLAN.analysesPerMonth} reports a month on Pro, with ${PLAN.creditPackSize}-report credit packs when you need more.`,
  },
};

export default function PricingPage() {
  return (
    <div className="wrap section">
      <p className="eyebrow">Pricing</p>
      <h1>One subscription, plus credits when you need more</h1>
      <p className="lede">
        The app records and stores sessions for free. Transcription and analysis run on
        our servers, which is what a subscription pays for — provider keys stay on the
        server and never ship inside the app.
      </p>

      <div className="plans">
        <div className="plan">
          <h2 style={{ fontSize: "1.3rem" }}>Free</h2>
          <p className="price">
            $0 <small>/ forever</small>
          </p>
          <p className="small muted" style={{ marginBottom: 0 }}>
            Everything that runs on your own machine.
          </p>
          <ul>
            <li>Record screen and narration</li>
            <li>Frame extraction and duplicate removal</li>
            <li>Browse and re-open past sessions</li>
            <li>No account required to record</li>
          </ul>
          <Link href="/download" className="btn">
            Download
          </Link>
        </div>

        <div className="plan featured">
          <h2 style={{ fontSize: "1.3rem" }}>Pro</h2>
          <p className="price">
            $29 <small>/ month</small>
          </p>
          <p className="small muted" style={{ marginBottom: 0 }}>
            Cloud transcription and AI analysis.
          </p>
          <ul>
            {PRO_FEATURES.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
          <Link href="/account" className="btn primary">
            Create an account
          </Link>
        </div>

        <div className="plan">
          <h2 style={{ fontSize: "1.3rem" }}>Credit packs</h2>
          <p className="price">
            +{PLAN.creditPackSize} <small>/ reports</small>
          </p>
          <p className="small muted" style={{ marginBottom: 0 }}>
            For months that run long. Requires an active subscription.
          </p>
          <ul>
            <li>Used only after the monthly allowance is spent</li>
            <li>One-off purchase, not a recurring charge</li>
            <li>Credits do not expire at the end of the month</li>
            <li>A failed report returns its credit</li>
          </ul>
          <Link href="/account" className="btn">
            Buy from your account
          </Link>
        </div>
      </div>

      <hr className="sprocket" style={{ margin: "3rem 0 2rem" }} />

      <h2>How usage is counted</h2>
      <div className="stack" style={{ maxWidth: "62ch" }}>
        <p>
          A report is charged when it succeeds. If analysis fails, you are not
          charged — and if a credit paid for it, the credit comes back.
        </p>
        <p>
          The monthly allowance resets at the start of each month. Credits do not: they
          sit on your account until used.
        </p>
        <p className="muted small">
          There is also a generous monthly processing-minutes ceiling as an abuse
          guard. It is not the limit you will meet in normal use — reports are.
        </p>
      </div>
    </div>
  );
}
