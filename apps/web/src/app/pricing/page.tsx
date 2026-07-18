import Link from "next/link";
import { SiteNav } from "@/components/SiteNav";
import { PLAN, PRO_FEATURES } from "@/lib/plans";

export default function PricingPage() {
  return (
    <div className="page">
      <SiteNav />
      <section className="section">
        <h3>Pricing</h3>
        <p>
          Download free. Cloud transcription and AI analysis require Pro. Keys stay on our
          servers — never inside the app.
        </p>
        <div className="pricing">
          <div className="price-card">
            <strong>Free</strong>
            <div className="price">
              $0 <small>/ forever</small>
            </div>
            <p className="muted" style={{ color: "var(--muted)" }}>
              Download the app, record locally, browse sessions. AI pipeline locked until
              you subscribe.
            </p>
            <p style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
              Pro includes {PLAN.analysesPerMonth} reports a month, up to{" "}
              {PLAN.maxFramesPerSession} screenshots each.
            </p>
            <Link href="/download" className="btn" style={{ marginTop: "1rem" }}>
              Download
            </Link>
          </div>
          <div className="price-card featured">
            <strong>Pro</strong>
            <div className="price">
              $29 <small>/ month</small>
            </div>
            <ul style={{ color: "var(--muted)", lineHeight: 1.6, paddingLeft: "1.1rem" }}>
              {PRO_FEATURES.map((feature) => (
                <li key={feature}>{feature}</li>
              ))}
            </ul>
            <Link href="/account" className="btn primary" style={{ marginTop: "1rem" }}>
              Create account &amp; subscribe
            </Link>
            <p style={{ color: "var(--muted)", fontSize: "0.85rem", marginTop: "0.75rem" }}>
              Or create an account, download reenigne, and click <em>Start subscription</em>.
            </p>
          </div>
        </div>
      </section>
      <footer className="footer">
        <Link href="/">← reenigne</Link>
      </footer>
    </div>
  );
}
