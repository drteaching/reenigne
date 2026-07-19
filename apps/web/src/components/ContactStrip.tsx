/**
 * The contact strip — the site's signature device.
 *
 * A run of extracted frames as the worker's manifest actually describes them:
 * an index, a timestamp, and whether the perceptual-hash dedupe kept or
 * dropped it. Dropped frames are struck through in grease-pencil red, which
 * is the whole idea — this is evidence, marked up.
 *
 * Purely decorative: the frames are CSS, not images, so the strip costs no
 * requests and no layout shift. Hidden from assistive tech, with the same
 * information given in prose nearby.
 */

export type Frame = {
  /** Frame number as it appears in the manifest and in report citations. */
  n: number;
  /** Seconds into the recording. */
  t: number;
  /** False when the phash dedupe dropped this frame as a near-duplicate. */
  kept?: boolean;
};

function timecode(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = (seconds % 60).toFixed(1).padStart(4, "0");
  return `${String(m).padStart(2, "0")}:${s}`;
}

export function ContactStrip({ frames }: { frames: Frame[] }) {
  return (
    <div className="strip" aria-hidden="true">
      {frames.map((f, i) => (
        <div
          key={f.n}
          className={`strip-cell ${f.kept === false ? "dropped" : "kept"}`}
          style={{ ["--i" as string]: i }}
        >
          <div className="strip-thumb">
            {f.kept === false && <span className="strip-strike" />}
          </div>
          <div className="strip-meta">
            <strong>#{String(f.n).padStart(3, "0")}</strong>
            <span>{timecode(f.t)}</span>
          </div>
        </div>
      ))}
    </div>
  );
}
