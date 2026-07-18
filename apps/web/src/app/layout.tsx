import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "reenigne — Reverse-engineer any product",
  description:
    "Record screen + narration. Get an AI teardown report. Download for Mac and Windows.",
  metadataBase: new URL("https://reenigne.dev"),
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
