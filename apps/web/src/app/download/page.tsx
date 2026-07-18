import Link from "next/link";
import { SiteNav } from "@/components/SiteNav";

const RELEASES =
  process.env.NEXT_PUBLIC_RELEASES_URL ||
  "https://github.com/reenigne/reenigne/releases/latest";

export default function DownloadPage() {
  return (
    <div className="page">
      <SiteNav />
      <section className="section">
        <h3>Download reenigne</h3>
        <p>
          Universal macOS (Apple Silicon + Intel) and Windows x64. No API keys in the
          installer — sign in after install.
        </p>
        <div className="pricing" style={{ marginTop: "2rem" }}>
          <div className="price-card featured">
            <strong>macOS</strong>
            <p style={{ color: "var(--muted)" }}>
              Universal binary · macOS 12+ · Screen Recording + Microphone permission
              required
            </p>
            <a
              className="btn primary"
              href={`${RELEASES}/download/reenigne-mac-universal.dmg`}
              style={{ marginTop: "1rem" }}
            >
              Download .dmg
            </a>
          </div>
          <div className="price-card">
            <strong>Windows</strong>
            <p style={{ color: "var(--muted)" }}>Windows 10/11 x64 · NSIS installer</p>
            <a
              className="btn primary"
              href={`${RELEASES}/download/reenigne-win-x64.exe`}
              style={{ marginTop: "1rem" }}
            >
              Download .exe
            </a>
          </div>
        </div>
        <p style={{ color: "var(--muted)", marginTop: "2rem" }}>
          All releases:{" "}
          <a href={RELEASES} style={{ color: "var(--accent)" }}>
            GitHub Releases
          </a>
          . Prefer CLI?{" "}
          <Link href="/docs" style={{ color: "var(--accent)" }}>
            See docs
          </Link>
          .
        </p>
      </section>
    </div>
  );
}
