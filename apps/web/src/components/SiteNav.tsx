import Link from "next/link";

const LINKS = [
  { href: "/sample-report", label: "Sample report" },
  { href: "/pricing", label: "Pricing" },
  { href: "/docs", label: "Docs" },
  { href: "/feedback", label: "Feedback" },
  { href: "/account", label: "Account" },
];

export function SiteNav() {
  return (
    <header className="nav">
      <div className="wrap nav-inner">
        <Link href="/" className="wordmark">
          reenigne
        </Link>
        <nav className="nav-links" aria-label="Main">
          {LINKS.map((l) => (
            <Link key={l.href} href={l.href}>
              {l.label}
            </Link>
          ))}
          <Link href="/download" className="btn primary" style={{ padding: "0.45rem 0.9rem" }}>
            Download
          </Link>
        </nav>
      </div>
    </header>
  );
}
