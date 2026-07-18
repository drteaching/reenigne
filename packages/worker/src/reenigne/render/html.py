"""Render a self-contained HTML report bundling screenshots + analysis."""

from __future__ import annotations

import base64
import html
from pathlib import Path
from typing import Optional

from ..models.session import Session


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>reenigne — {target}</title>
<style>
  :root {{
    --bg: #0f1115;
    --panel: #171a21;
    --border: #2a2f3a;
    --text: #e6e6e6;
    --muted: #98a1b3;
    --accent: #4ea1ff;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg); color: var(--text);
    margin: 0; padding: 0;
  }}
  header {{
    padding: 2rem 3rem; border-bottom: 1px solid var(--border);
    background: linear-gradient(180deg, #171a21, #0f1115);
  }}
  h1 {{ margin: 0 0 .5rem 0; font-size: 2rem; }}
  .meta {{ color: var(--muted); font-size: .9rem; }}
  .container {{ display: grid; grid-template-columns: 300px 1fr; min-height: 100vh; }}
  aside {{
    border-right: 1px solid var(--border); padding: 1rem;
    max-height: 100vh; overflow-y: auto; position: sticky; top: 0;
  }}
  aside h3 {{ font-size: .8rem; text-transform: uppercase; color: var(--muted); }}
  .frame-strip {{ display: flex; flex-direction: column; gap: .5rem; }}
  .frame-strip img {{
    width: 100%; border-radius: 6px; border: 1px solid var(--border);
    cursor: pointer; transition: transform .15s;
  }}
  .frame-strip img:hover {{ transform: scale(1.02); border-color: var(--accent); }}
  .frame-label {{ font-size: .75rem; color: var(--muted); }}
  main {{ padding: 2rem 3rem; max-width: 1000px; }}
  main h2 {{
    border-bottom: 1px solid var(--border); padding-bottom: .3rem; margin-top: 2rem;
  }}
  pre {{
    background: var(--panel); padding: 1rem; border-radius: 6px;
    overflow-x: auto; font-size: .85rem;
  }}
  code {{ background: var(--panel); padding: 2px 6px; border-radius: 3px; }}
  blockquote {{
    border-left: 3px solid var(--accent);
    padding-left: 1rem; color: var(--muted); font-style: italic;
  }}
  .gallery-frame {{ margin: 1rem 0; }}
  .gallery-frame img {{
    max-width: 100%; border-radius: 6px; border: 1px solid var(--border);
  }}
  .gallery-frame .caption {{
    font-size: .85rem; color: var(--muted); padding: .5rem 0;
  }}
  a {{ color: var(--accent); }}
</style>
</head>
<body>
<header>
  <h1>reenigne Teardown — {target}</h1>
  <div class="meta">
    Recorded {started_at} · Duration {duration:.1f}s · {frame_count} frames
  </div>
</header>

<div class="container">
  <aside>
    <h3>Screenshots</h3>
    <div class="frame-strip">
      {frame_strip}
    </div>
  </aside>
  <main>
    <h2>📝 AI Analysis</h2>
    {analysis_html}

    <h2>📸 Screenshot Gallery</h2>
    {gallery_html}
  </main>
</div>
</body>
</html>
"""


# Tags we allow through from rendered markdown. Reports get shared, and both
# the analysis text (LLM output) and the narration (Whisper output) are
# ultimately derived from whatever was on screen — treat both as untrusted.
_ALLOWED_TAGS = [
    "p", "br", "hr", "pre", "code", "blockquote",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "strong", "em", "del",
    "table", "thead", "tbody", "tr", "th", "td",
]


def _md_to_html(md: str) -> str:
    """Render markdown to sanitized HTML."""
    try:
        import markdown
    except ImportError:
        return "<pre>" + html.escape(md) + "</pre>"

    rendered = markdown.markdown(md, extensions=["fenced_code", "tables"])

    try:
        import bleach
    except ImportError:
        # Without a sanitizer we cannot safely emit raw HTML.
        print(
            "[render] WARNING: bleach not installed; rendering analysis as "
            "plain text. Install it with: pip install bleach"
        )
        return "<pre>" + html.escape(md) + "</pre>"

    return bleach.clean(rendered, tags=_ALLOWED_TAGS, attributes={}, strip=True)


def render_html_report(
    session: Session,
    session_dir: Path,
    analysis_markdown: str,
    output_path: Optional[Path] = None,
) -> Path:
    """Emit report.html with all screenshots embedded as base64."""
    output_path = output_path or session_dir / "report.html"

    frames = [f for f in session.frames if not f.is_duplicate]

    # Build strip and gallery
    strip_parts = []
    gallery_parts = []
    for f in frames:
        img_file = session_dir / f.path
        if not img_file.exists():
            continue
        b64 = base64.b64encode(img_file.read_bytes()).decode("utf-8")
        data_uri = f"data:image/png;base64,{b64}"

        strip_parts.append(
            f'<div><img src="{data_uri}" alt="frame {f.index}" '
            f'onclick="document.getElementById(\'frame-{f.index}\').scrollIntoView({{behavior:\'smooth\'}})">'
            f'<div class="frame-label">#{f.index} · {f.timestamp_seconds:.0f}s</div></div>'
        )

        narration = (
            html.escape(f.narration)
            if f.narration
            else "<em>(no narration)</em>"
        )
        gallery_parts.append(f"""
        <div class="gallery-frame" id="frame-{f.index}">
          <img src="{data_uri}" alt="frame {f.index}">
          <div class="caption"><strong>Frame #{f.index}</strong> · {f.timestamp_seconds:.1f}s<br>
          {narration}</div>
        </div>
        """)

    html_out = HTML_TEMPLATE.format(
        target=html.escape(session.target),
        started_at=html.escape(str(session.started_at)),
        duration=session.duration_seconds,
        frame_count=len(frames),
        frame_strip="\n".join(strip_parts),
        analysis_html=_md_to_html(analysis_markdown),
        gallery_html="\n".join(gallery_parts),
    )

    output_path.write_text(html_out, encoding="utf-8")
    return output_path
