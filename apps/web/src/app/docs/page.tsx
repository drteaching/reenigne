import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Docs — quickstart",
  description:
    "Record, process, analyse and render a teardown from the reenigne desktop app or the command line.",
};

export default function DocsPage() {
  return (
    <div className="wrap section">
      <p className="eyebrow">Documentation</p>
      <h1>Quickstart</h1>
      <p className="lede">
        The desktop app runs the whole pipeline behind one button. The CLI exposes the
        same four stages separately, which is what you want when re-analysing a
        session you already recorded.
      </p>

      <h2 style={{ marginTop: "2.5rem" }}>Desktop</h2>
      <ol className="stack" style={{ paddingLeft: "1.2rem", maxWidth: "62ch" }}>
        <li>Sign in on the Account tab. Recording works signed out; analysis does not.</li>
        <li>
          Enter the product name you are about to explore, then start recording. On
          macOS, grant Screen Recording and Microphone permission and restart the app.
        </li>
        <li>
          Narrate as you go. What you say is transcribed and aligned to the frame that
          was on screen when you said it — that alignment is what makes the report
          specific.
        </li>
        <li>
          Stop. The app extracts frames, transcribes, analyses and opens the rendered
          HTML report.
        </li>
      </ol>

      <h2 style={{ marginTop: "2.5rem" }}>Command line</h2>
      <p>
        Install the worker package and point it at the API. A token comes from{" "}
        <code>POST /v1/auth/login</code> or from signing in on the desktop app.
      </p>

      <div className="readout">
        <pre>
          <code>{`cd packages/worker
pip install -e ".[dev]"

export REENIGNE_API_URL=https://api.reenigne.dev
export REENIGNE_API_TOKEN=<your token>`}</code>
        </pre>
      </div>

      <h3 style={{ marginTop: "2rem" }}>The whole pipeline in one command</h3>
      <div className="readout">
        <pre>
          <code>{`reenigne pipeline --target "Meridian"`}</code>
        </pre>
      </div>
      <p className="small muted">
        Records until you press Ctrl+C, then processes, analyses and renders. Accepts{" "}
        <code>--output</code>, <code>--model</code>, <code>--prompt</code> and{" "}
        <code>--interval</code>.
      </p>

      <h3 style={{ marginTop: "2rem" }}>Or one stage at a time</h3>
      <div className="readout">
        <pre>
          <code>{`# 1. Record. Ctrl+C to stop.
reenigne record --target "Meridian"

# 2. Extract frames, transcribe, align.
reenigne process ~/reenigne/meridian-20260718-142203

# 3. Analyse. Templates: teardown, ux, features, tech-stack.
reenigne analyze ~/reenigne/meridian-20260718-142203 --prompt teardown

# 4. Render. Formats: html, md, json.
reenigne report ~/reenigne/meridian-20260718-142203 --format html`}</code>
        </pre>
      </div>

      <h3 style={{ marginTop: "2rem" }}>Useful flags</h3>
      <table className="feature-table" style={{ marginTop: "1rem" }}>
        <thead>
          <tr>
            <th scope="col">Flag</th>
            <th scope="col">Command</th>
            <th scope="col">What it does</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row" className="mono small" style={{ textTransform: "none", letterSpacing: 0 }}>
              --interval
            </th>
            <td className="mono small muted">record, pipeline</td>
            <td className="muted">Seconds between captured frames. Default 3.</td>
          </tr>
          <tr>
            <th scope="row" className="mono small" style={{ textTransform: "none", letterSpacing: 0 }}>
              --display
            </th>
            <td className="mono small muted">record</td>
            <td className="muted">Display index, when you have more than one screen.</td>
          </tr>
          <tr>
            <th scope="row" className="mono small" style={{ textTransform: "none", letterSpacing: 0 }}>
              --force
            </th>
            <td className="mono small muted">process</td>
            <td className="muted">Re-extract frames even if the manifest already has them.</td>
          </tr>
          <tr>
            <th scope="row" className="mono small" style={{ textTransform: "none", letterSpacing: 0 }}>
              --no-ocr
            </th>
            <td className="mono small muted">process</td>
            <td className="muted">Skip OCR. Faster, and needed if tesseract is not installed.</td>
          </tr>
          <tr>
            <th scope="row" className="mono small" style={{ textTransform: "none", letterSpacing: 0 }}>
              --model
            </th>
            <td className="mono small muted">analyze, pipeline</td>
            <td className="muted">Override the analysis model. Defaults to grok-4.</td>
          </tr>
        </tbody>
      </table>

      <h2 style={{ marginTop: "2.5rem" }}>Reporting a problem</h2>
      <p>
        <code>reenigne feedback</code> opens a short prompt and files a report, or use
        the <Link href="/feedback">form</Link>. Reports are triaged automatically. Do
        not paste API keys or tokens — submissions containing them are rejected before
        being stored.
      </p>

      <h2 style={{ marginTop: "2.5rem" }}>What leaves your machine</h2>
      <div className="stack" style={{ maxWidth: "62ch" }}>
        <p>
          The recording itself never does. Extracted frames are downscaled and
          JPEG-encoded before upload, and only the deduplicated set is sent.
        </p>
        <p>
          Audio is extracted and sent for transcription. See{" "}
          <Link href="/legal/privacy">the privacy notice</Link> for the full data path.
        </p>
      </div>
    </div>
  );
}
