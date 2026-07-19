"""Command-line interface for reenigne."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import click

from . import __version__
from .config import Config
from .pipeline import cmd_analyze, cmd_process, cmd_record, cmd_report


@click.group()
@click.version_option(__version__)
def main():
    """reenigne — Record, narrate, and AI-analyze any product workflow."""
    pass


@main.command()
@click.option(
    "--target",
    "-t",
    required=True,
    help="Name of the product/site being analyzed (e.g. 'Heidi Health')",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Session directory (default: ~/reenigne/<target>-<timestamp>)",
)
@click.option("--interval", type=float, default=None, help="Frame interval seconds")
@click.option("--display", type=int, default=None, help="Display index (platform-specific)")
def record(target, output, interval, display):
    """Start a new recording session. Ctrl+C to stop."""
    cfg = Config.from_env()
    if interval is not None:
        cfg.frame_interval_seconds = interval
    if output:
        session_dir = Path(output)
    else:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe = "".join(c for c in target if c.isalnum() or c in "-_").lower()
        session_dir = cfg.output_root / f"{safe}-{stamp}"

    cmd_record(
        target=target,
        session_dir=session_dir,
        cfg=cfg,
        display=display,
    )
    click.secho(
        f"\nRecording saved. Next: reenigne process {session_dir}",
        fg="green",
    )


@main.command()
@click.argument("session_dir", type=click.Path(exists=True))
@click.option("--force", is_flag=True, help="Re-process even if manifest has frames")
@click.option("--no-ocr", is_flag=True, help="Skip OCR")
def process(session_dir, force, no_ocr):
    """Extract frames, transcribe, align. Runs after `record`."""
    cfg = Config.from_env()
    if no_ocr:
        cfg.enable_ocr = False
    cmd_process(Path(session_dir), cfg, force=force)
    click.secho(
        f"\nProcessed. Next: reenigne analyze {session_dir}",
        fg="green",
    )


@main.command()
@click.argument("session_dir", type=click.Path(exists=True))
@click.option(
    "--model",
    "-m",
    default=None,
    help="LLM model (default: grok-4; fallbacks: gpt-4o, claude-sonnet-4-5)",
)
@click.option(
    "--prompt",
    "-p",
    default="teardown",
    type=click.Choice(["teardown", "ux", "features", "tech-stack"]),
)
def analyze(session_dir, model, prompt):
    """Send session bundle to cloud LLM for reverse-engineering."""
    cfg = Config.from_env()
    cmd_analyze(Path(session_dir), cfg, model=model, prompt=prompt)
    click.secho(
        f"\nAnalysis done. Next: reenigne report {session_dir}",
        fg="green",
    )


@main.command()
@click.argument("session_dir", type=click.Path(exists=True))
@click.option(
    "--format",
    "fmt",
    default="html",
    type=click.Choice(["html", "md", "json"]),
    help="Output format",
)
def report(session_dir, fmt):
    """Render report (html/md/json)."""
    path = cmd_report(Path(session_dir), fmt=fmt)
    click.secho(f"\nReport ready: {path}", fg="green")


@main.command()
@click.option("--target", "-t", required=True)
@click.option("--output", "-o", type=click.Path())
@click.option("--model", "-m", default=None)
@click.option("--prompt", "-p", default="teardown")
@click.option("--interval", type=float, default=None)
def pipeline(target, output, model, prompt, interval):
    """Record → process → analyze → report, in one shot."""
    cfg = Config.from_env()
    if interval is not None:
        cfg.frame_interval_seconds = interval
    if output:
        session_dir = Path(output)
    else:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe = "".join(c for c in target if c.isalnum() or c in "-_").lower()
        session_dir = cfg.output_root / f"{safe}-{stamp}"

    cmd_record(target, session_dir, cfg)
    cmd_process(session_dir, cfg)
    cmd_analyze(session_dir, cfg, model=model, prompt=prompt)
    cmd_report(session_dir)
    click.secho(
        f"\nFull pipeline complete: {session_dir}",
        fg="green",
        bold=True,
    )


@main.command()
@click.option(
    "--kind",
    type=click.Choice(["bug", "improvement"]),
    default=None,
    help="Skip the prompt and set the kind directly.",
)
@click.option("--title", default=None, help="Skip the prompt and set the title.")
def feedback(kind, title):
    """Report a bug or suggest an improvement."""
    from .cloud import CloudAPIError, CloudClient

    cfg = Config.from_env()
    client = CloudClient(cfg.api_base_url, cfg.api_token or "")

    kind = kind or click.prompt(
        "What kind of feedback",
        type=click.Choice(["bug", "improvement"]),
        default="bug",
    )
    title = title or click.prompt("One-line summary")
    click.echo("Describe it (finish with an empty line):")
    lines = []
    while True:
        line = click.prompt("", default="", show_default=False, prompt_suffix="  ")
        if not line.strip():
            break
        lines.append(line)
    description = "\n".join(lines).strip()
    if not description:
        click.secho("Nothing to send — a description is required.", fg="red")
        raise SystemExit(1)

    context = {}
    if click.confirm("Attach app version and OS?", default=True):
        import platform as _platform

        context = {
            "app_version": __version__,
            "platform": _platform.system().lower(),
            "os": _platform.platform(),
        }

    if not cfg.api_token:
        click.secho("Not signed in — submitting anonymously.", fg="yellow")

    try:
        result = client.submit_feedback(
            kind=kind, title=title, description=description, context=context
        )
    except CloudAPIError as e:
        # The API explains rejections (a detected secret, a rate limit) in
        # terms the submitter can act on; show that rather than a stack trace.
        click.secho(f"\nNot submitted: {e}", fg="red")
        raise SystemExit(1)

    click.secho(f"\nThanks — submitted ({result.get('id', '')}).", fg="green")
    click.echo("It will be triaged automatically. No recordings were attached.")


if __name__ == "__main__":
    main()
