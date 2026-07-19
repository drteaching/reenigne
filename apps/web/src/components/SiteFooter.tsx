import Link from "next/link";

export function SiteFooter() {
  return (
    <footer className="footer">
      <div className="wrap footer-inner">
        <div>
          <p className="mono small" style={{ marginBottom: "0.35rem" }}>
            reenigne
          </p>
          <p className="small" style={{ margin: 0, maxWidth: "34ch" }}>
            An instrument for studying software. Built in Australia.
          </p>
        </div>
        <nav aria-label="Footer">
          <Link href="/sample-report">Sample report</Link>
          <Link href="/pricing">Pricing</Link>
          <Link href="/docs">Docs</Link>
          <Link href="/download">Download</Link>
          <Link href="/feedback">Feedback</Link>
          <Link href="/legal/privacy">Privacy</Link>
          <Link href="/legal/terms">Terms</Link>
        </nav>
      </div>
      <div className="wrap">
        <p className="small muted" style={{ marginTop: "1.5rem", marginBottom: 0 }}>
          © {new Date().getFullYear()} reenigne. Recording third-party software may be
          restricted by their terms of service — check before you record.
        </p>
      </div>
    </footer>
  );
}
