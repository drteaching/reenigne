import Link from "next/link";

export function SiteNav() {
  return (
    <nav className="nav">
      <Link href="/" className="logo">
        reenigne
      </Link>
      <div className="nav-links">
        <Link href="/#how">How it works</Link>
        <Link href="/pricing">Pricing</Link>
        <Link href="/docs">Docs</Link>
        <Link href="/account">Account</Link>
        <Link href="/download" className="btn primary">
          Download
        </Link>
      </div>
    </nav>
  );
}
