import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt = "reenigne — record a product walkthrough, get a teardown";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

/** Shares the site's palette: photo-paper ground, graphite ink, grease-pencil red. */
export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          background: "#EDEDEA",
          color: "#1A1D21",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: 72,
          fontFamily: "sans-serif",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 14, fontSize: 26 }}>
          <div style={{ width: 16, height: 16, borderRadius: 8, background: "#C8352A" }} />
          reenigne
        </div>
        <div style={{ display: "flex", flexDirection: "column" }}>
          <div style={{ fontSize: 82, lineHeight: 1.03, letterSpacing: -2, maxWidth: 940 }}>
            Record a walkthrough. Get the teardown.
          </div>
          <div style={{ fontSize: 30, color: "#5A6169", marginTop: 26, maxWidth: 900 }}>
            Feature inventory, workflow analysis and an inferred data model — every
            observation cited to the frame it came from.
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
            <div
              key={i}
              style={{
                width: 116,
                height: 72,
                background: i % 3 === 2 ? "#3A3F47" : "#23272D",
                borderRadius: 3,
                opacity: i % 3 === 2 ? 0.45 : 1,
              }}
            />
          ))}
        </div>
      </div>
    ),
    size
  );
}
