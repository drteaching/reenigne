import { useCallback, useEffect, useState } from "react";

/**
 * macOS first-run permission flow.
 *
 * Shown on the Record tab whenever screen or microphone access is not
 * granted, because that is where the blocked action lives — it sits above the
 * recorder rather than becoming a fifth tab competing with Feedback.
 *
 * State is re-read from the system on every mount, never stored. A "we
 * onboarded them already" flag would be wrong the moment someone revokes
 * access in System Settings, which is exactly when this panel is most needed.
 */

type Status = {
  platform: string;
  microphone: MediaAccessStatus;
  screen: MediaAccessStatus;
};

export function usePermissionStatus() {
  const [status, setStatus] = useState<Status | null>(null);

  const refresh = useCallback(async () => {
    if (!window.reenigne?.permStatus) return;
    setStatus(await window.reenigne.permStatus());
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Non-macOS platforms report granted, so this is false there.
  const needsSetup =
    !!status && (status.screen !== "granted" || status.microphone !== "granted");

  return { status, needsSetup, refresh };
}

function Pill({ state }: { state: MediaAccessStatus }) {
  const label =
    state === "granted" ? "granted" : state === "denied" ? "denied" : "not yet asked";
  return (
    <span className={`badge ${state === "granted" ? "" : "warn"}`}>{label}</span>
  );
}

export function SetupPanel({
  status,
  onChanged,
}: {
  status: Status;
  onChanged: () => void;
}) {
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<PreflightResult | null>(null);

  async function testPermissions() {
    setTesting(true);
    setResult(null);
    try {
      // Microphone first: askForMediaAccess raises the prompt from the app
      // process itself, so it attributes to reenigne by construction and
      // needs no capture. Screen recording has no request API — the only way
      // to provoke that prompt is to attempt a real capture, which is what
      // preflight does next.
      await window.reenigne.requestMicrophone();
      const res = (await window.reenigne.workerRpc("preflight")) as PreflightResult;
      setResult(res);
    } catch (err) {
      setResult({
        ffmpeg_found: false,
        ffmpeg_path: null,
        screen_ok: false,
        mic_ok: false,
        errors: [
          {
            reason: "other",
            message:
              "Could not run the permission check. The recorder component may " +
              "not have started.",
            detail: err instanceof Error ? err.message : String(err),
          },
        ],
      });
    } finally {
      setTesting(false);
      onChanged();
    }
  }

  return (
    <div className="panel setup-panel">
      <h2>Allow reenigne to record</h2>
      <p className="muted">
        macOS asks separately for the screen and the microphone. Both are needed:
        the screen becomes the frames, and your narration becomes the transcript
        that ties observations to them.
      </p>

      <ul className="perm-list">
        <li>
          <strong>Screen &amp; System Audio Recording</strong> <Pill state={status.screen} />
          <p className="muted small">
            macOS shows this prompt the first time reenigne captures. It only takes
            effect after the app restarts — that is macOS behaviour, not a bug.
          </p>
        </li>
        <li>
          <strong>Microphone</strong> <Pill state={status.microphone} />
          <p className="muted small">
            Prompted directly by the app. Applies immediately, no restart needed.
          </p>
        </li>
      </ul>

      <div className="row" style={{ gap: 8, marginTop: 12, flexWrap: "wrap" }}>
        <button className="btn primary" onClick={testPermissions} disabled={testing}>
          {testing ? "Testing…" : "Test permissions"}
        </button>
        <button
          className="btn"
          onClick={() => window.reenigne.openPermissionSettings("screen")}
        >
          Open Screen Recording settings
        </button>
        <button
          className="btn"
          onClick={() => window.reenigne.openPermissionSettings("microphone")}
        >
          Open Microphone settings
        </button>
      </div>

      <p className="muted small" style={{ marginTop: 8 }}>
        &ldquo;Test permissions&rdquo; records for one second to make macOS show the
        prompts now, rather than in the middle of your first real session. Nothing
        is kept.
      </p>

      {result && (
        <div style={{ marginTop: 12 }}>
          {result.errors.length === 0 ? (
            <p className="ok-note">
              <strong>All set.</strong> Screen and microphone capture both work.
            </p>
          ) : (
            result.errors.map((e, i) => (
              <div key={i} className="lock-banner" style={{ display: "block" }}>
                <p style={{ margin: 0 }}>{e.message}</p>
                {e.reason === "permission_denied" && (
                  <p className="muted small" style={{ margin: "6px 0 0" }}>
                    If you already granted it, quit and reopen reenigne — macOS
                    applies a new screen-recording grant only on relaunch.
                  </p>
                )}
                {e.detail && (
                  <details style={{ marginTop: 6 }}>
                    <summary className="muted small">Technical detail</summary>
                    <pre className="detail-pre">{e.detail}</pre>
                  </details>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
