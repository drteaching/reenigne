"""Report rendering must not emit untrusted content as live HTML."""

import tempfile
from pathlib import Path

from reenigne.models.frame import Frame
from reenigne.models.session import Session
from reenigne.render.html import render_html_report


def _render(target, narration, analysis):
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        s = Session(target=target, duration_seconds=1.0, frame_interval_seconds=3.0)
        s.frames = [
            Frame(index=1, path="missing.png", timestamp_seconds=0.0, narration=narration)
        ]
        out = render_html_report(s, d, analysis)
        return out.read_text(encoding="utf-8")


def test_target_is_escaped():
    html = _render("<script>alert(1)</script>", "", "")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_script_in_analysis_markdown_is_stripped():
    """The tag must not survive. Its inner text may, as inert plain text."""
    html = _render("App", "", "Findings\n\n<script>alert('xss')</script>\n")
    assert "<script" not in html
    assert "</script>" not in html


def test_event_handler_attribute_is_stripped():
    html = _render("App", "", '<p onclick="steal()">Findings</p>')
    assert "onclick" not in html
    assert "Findings" in html


def test_img_tag_in_analysis_is_stripped():
    """An <img> with a remote src would beacon on open."""
    html = _render("App", "", '<img src="https://evil.example/track.gif">')
    assert "evil.example" not in html


def test_markdown_formatting_survives_sanitization():
    html = _render("App", "", "# Heading\n\n- one\n- two\n\n**bold**\n")
    assert "<h1>Heading</h1>" in html
    assert "<li>one</li>" in html
    assert "<strong>bold</strong>" in html


def test_javascript_url_is_stripped():
    html = _render("App", "", "[click](javascript:alert(1))")
    assert "javascript:" not in html


def test_non_ascii_content_round_trips():
    """Regression: bare write_text() raised UnicodeEncodeError on Windows."""
    html = _render("Café — Über", "naïve 🎉", "Résumé ✅")
    assert "Café" in html
    assert "Résumé" in html
