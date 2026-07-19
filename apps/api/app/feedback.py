"""
User feedback intake.

Bug reports and improvement suggestions arrive from the desktop app, the CLI
and the public website. Intake stores them; a separate triage job (see
app/triage.py) classifies each one and may file a GitHub issue.

Nothing in this module touches quota, credits or billing. Feedback is free to
submit by design — charging for it, or letting it consume an analysis
allowance, would suppress exactly the reports we most want.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import DateTime, String, Text, Uuid, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from .config import Settings
from .db import Base

KIND_BUG = "bug"
KIND_IMPROVEMENT = "improvement"
KINDS = (KIND_BUG, KIND_IMPROVEMENT)

STATUS_RECEIVED = "received"
STATUS_TRIAGED = "triaged"
STATUS_FILED = "filed"
STATUS_DISMISSED = "dismissed"

MAX_TITLE = 200
MAX_DESCRIPTION = 5000
MAX_LOGS_EXCERPT = 10000


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    # Nullable: the public site accepts anonymous reports. Also cleared when
    # an account is deleted (ON DELETE SET NULL), so feedback outlives the
    # account in anonymised form — see the migration for the privacy note.
    user_id: Mapped[Optional[str]] = mapped_column(
        Uuid(as_uuid=False), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), default=KIND_BUG)
    title: Mapped[str] = mapped_column(String(MAX_TITLE), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    context_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        String(16), default=STATUS_RECEIVED, index=True
    )
    triage_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    github_issue_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # HMAC of the submitter's IP, never the address itself. Enough to count
    # anonymous submissions per source; not a location log. Keyed by
    # api_secret_key, so rotating that key resets anonymous windows —
    # acceptable, since the alternative is retaining raw addresses.
    submitter_ip_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "github_issue_url": self.github_issue_url,
        }


# ---------- Secret scanning ----------


class SecretDetected(Exception):
    """Raised when a submission carries something credential-shaped."""

    def __init__(self, name: str, guidance: str):
        self.name = name
        self.guidance = guidance
        super().__init__(guidance)


# (human-readable name, pattern). The name is surfaced to the submitter: a
# report bounced for an unexplained reason is a report we never receive.
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "Authorization header",
        re.compile(r"authorization\s*:\s*(bearer|basic)\s+\S+", re.IGNORECASE),
    ),
    (
        "API key",
        re.compile(r"\b(sk-|sk_live_|sk_test_|xai-)[A-Za-z0-9_\-]{16,}"),
    ),
    (
        "GitHub token",
        re.compile(r"\b(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"),
    ),
    (
        "webhook signing secret",
        re.compile(r"\bwhsec_[A-Za-z0-9_\-]{16,}"),
    ),
    (
        # Requires the full three-part structure. A bare "eyJ" in a pasted log
        # fragment is not a token and must not bounce a real bug report.
        "JSON Web Token",
        re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"),
    ),
]


def scan_for_secrets(*fields: str | None) -> None:
    """Raise SecretDetected on the first credential-shaped match."""
    for value in fields:
        if not value:
            continue
        for name, pattern in SECRET_PATTERNS:
            if pattern.search(value):
                raise SecretDetected(
                    name,
                    f"Your report looks like it contains a {name}, so it was "
                    f"not stored. Please replace that value with REDACTED and "
                    f"resubmit — we never want credentials in a bug report. "
                    f"If this is a false positive (for example the pattern "
                    f"appears inside prose or a truncated log line), redact or "
                    f"reword that fragment and it will go through.",
                )


def redact_secrets(text: str) -> str:
    """
    Blank anything credential-shaped. Defence in depth for content that is
    about to leave the system — intake already rejects these, but the triage
    model's output and any stored context go through here before reaching
    GitHub.
    """
    for name, pattern in SECRET_PATTERNS:
        text = pattern.sub(f"[REDACTED {name}]", text)
    return text


# ---------- Rate limiting ----------


def hash_ip(ip: str | None, settings: Settings) -> str | None:
    if not ip:
        return None
    return hmac.new(
        settings.api_secret_key.encode(), ip.encode(), hashlib.sha256
    ).hexdigest()


async def count_recent(
    session: AsyncSession,
    *,
    user_id: str | None = None,
    ip_hash: str | None = None,
    hours: int = 24,
) -> int:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = select(func.count()).select_from(Feedback).where(Feedback.created_at >= since)
    if user_id is not None:
        stmt = stmt.where(Feedback.user_id == str(user_id))
    else:
        stmt = stmt.where(Feedback.user_id.is_(None), Feedback.submitter_ip_hash == ip_hash)
    return int((await session.execute(stmt)).scalar_one())


async def create_feedback(
    session: AsyncSession,
    *,
    user_id: str | None,
    kind: str,
    title: str,
    description: str,
    context: dict[str, Any] | None,
    ip_hash: str | None,
) -> Feedback:
    row = Feedback(
        id=str(uuid.uuid4()),
        user_id=str(user_id) if user_id else None,
        kind=kind,
        title=title,
        description=description,
        context_json=json.dumps(context or {}),
        status=STATUS_RECEIVED,
        submitter_ip_hash=ip_hash,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row
