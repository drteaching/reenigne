import type { Metadata } from "next";
import Link from "next/link";
import { DownloadPicker } from "@/components/DownloadPicker";

export const metadata: Metadata = {
  title: "Download",
  description:
    "reenigne for macOS (Apple Silicon and Intel) and Windows x64. Record locally; analysis runs on our servers with a subscription.",
};

export default function DownloadPage() {
  return (
    <div className="wrap section">
      <p className="eyebrow">Download</p>
      <h1>Get reenigne</h1>
      <p className="lede">
        The desktop app records, extracts frames and runs the pipeline. macOS universal
        (Apple Silicon and Intel) and Windows x64.
      </p>

      <DownloadPicker />

      <hr className="sprocket" style={{ margin: "3rem 0 2rem" }} />

      <h2>Before you record</h2>
      <div className="stack" style={{ maxWidth: "62ch" }}>
        <p>
          <strong>macOS</strong> asks for Screen Recording and Microphone permission the
          first time. Both live in System Settings › Privacy &amp; Security; the app has
          to be restarted after granting them.
        </p>
        <p>
          <strong>ffmpeg</strong> is bundled with the packaged app. If you run the CLI
          from source you will need it on your PATH.
        </p>
        <p className="muted">
          Recording third-party software may be restricted by that product&rsquo;s terms
          of service. Check before you record something you do not own.
        </p>
      </div>

      <h2 style={{ marginTop: "2.5rem" }}>Prefer the command line?</h2>
      <p>
        The same pipeline runs from a terminal. See the{" "}
        <Link href="/docs">quickstart</Link>.
      </p>
    </div>
  );
}
