"""
Standalone job runner.

    python -m app.runner_loop

The recommended way to execute analysis jobs. A long-running process has no
invocation ceiling, so a provider call cannot be killed part-way through —
which on a capped platform wastes the tokens the attempt already spent and
leaves the job to sit until its lease lapses.

Deploy this alongside the API with the same environment (it needs
DATABASE_URL and the provider keys; it does not serve HTTP). On Fly or
Railway that is a second process in the same app.

Prefer this over:
  - JOB_RUN_INLINE, which blocks the submit request for the whole analysis
    and is dev-only.
  - The cron trigger, which is bounded by the platform's maxDuration and by
    how often the scheduler fires.
"""

from __future__ import annotations

import asyncio
import logging
import signal

from .config import get_settings
from .db import init_db
from .jobs import run_one_job

log = logging.getLogger("reenigne.runner")

_shutdown = asyncio.Event()


def _request_shutdown(*_args) -> None:
    log.info("shutdown requested; finishing current job then exiting")
    _shutdown.set()


async def run_forever() -> None:
    settings = get_settings()
    settings.validate_runtime()
    await init_db()

    log.info(
        "runner started (idle_sleep=%ss, lease=%ss, max_attempts=%s)",
        settings.job_runner_idle_sleep_seconds,
        settings.job_lease_seconds,
        settings.job_max_attempts,
    )

    while not _shutdown.is_set():
        try:
            job_id = await run_one_job(settings)
        except Exception:
            # A crash here must not kill the loop; the job's lease will lapse
            # and it becomes claimable again.
            log.exception("runner iteration failed")
            job_id = None

        if job_id:
            log.info("completed job %s", job_id)
            continue  # drain greedily while there is work

        # Queue empty: wait, but stay responsive to shutdown.
        try:
            await asyncio.wait_for(
                _shutdown.wait(), timeout=settings.job_runner_idle_sleep_seconds
            )
        except asyncio.TimeoutError:
            pass

    log.info("runner stopped")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_shutdown)
        except NotImplementedError:  # pragma: no cover - Windows
            signal.signal(sig, _request_shutdown)

    try:
        loop.run_until_complete(run_forever())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
