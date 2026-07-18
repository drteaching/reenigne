import { SiteNav } from "@/components/SiteNav";

export default function LegalPage() {
  return (
    <div className="page">
      <SiteNav />
      <section className="section">
        <h3>Legal &amp; disclaimer</h3>
        <p style={{ color: "var(--muted)", lineHeight: 1.7 }}>
          reenigne is a research tool. Recording commercial SaaS products may violate the
          target&apos;s Terms of Service. Do not record sessions containing real patient
          data, credentials, or other sensitive PII. You are responsible for complying with
          applicable law and third-party agreements. Screenshots and transcripts sent for AI
          analysis are processed by our cloud providers (xAI, OpenAI, Anthropic) under their
          respective terms.
        </p>
      </section>
    </div>
  );
}
