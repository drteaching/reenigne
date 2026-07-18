import Link from "next/link";
import { SiteNav } from "@/components/SiteNav";

export default function DocsPage() {
  return (
    <div className="page">
      <SiteNav />
      <section className="section">
        <h3>Docs</h3>
        <p>Get from install to first teardown in under five minutes.</p>

        <h4 style={{ marginTop: "2rem" }}>Desktop app</h4>
        <ol style={{ color: "var(--muted)", lineHeight: 1.7 }}>
          <li>
            <Link href="/download" style={{ color: "var(--accent)" }}>
              Download
            </Link>{" "}
            for Mac or Windows and install.
          </li>
          <li>
            On macOS: grant <strong>Screen Recording</strong> and <strong>Microphone</strong>{" "}
            in System Settings → Privacy &amp; Security.
          </li>
          <li>Sign in with your reenigne account (or create one).</li>
          <li>Subscribe (or start trial) to unlock cloud AI.</li>
          <li>Enter a product name → Record → explore while narrating → Stop.</li>
          <li>reenigne processes locally, then calls the cloud for Whisper + Grok.</li>
        </ol>

        <h4 style={{ marginTop: "2rem" }}>CLI (power users)</h4>
        <pre
          style={{
            background: "#12171c",
            padding: "1rem",
            borderRadius: 12,
            overflow: "auto",
            border: "1px solid var(--line)",
          }}
        >{`pip install -e packages/worker
export REENIGNE_API_URL=https://api.reenigne.dev
export REENIGNE_API_TOKEN=<jwt from login>
reenigne record --target "Competitor"
reenigne process ~/reenigne/...
reenigne analyze ~/reenigne/...
reenigne report ~/reenigne/...`}</pre>

        <h4 style={{ marginTop: "2rem" }}>Privacy</h4>
        <p style={{ color: "var(--muted)" }}>
          Raw video stays on your machine. Only audio (transcription) and selected
          screenshots + narration are sent to reenigne cloud for AI processing. Provider
          API keys never ship inside the download.
        </p>
      </section>
    </div>
  );
}
