"""
GitHub issue filing for triaged feedback.

Degrades cleanly: with GITHUB_FEEDBACK_TOKEN or GITHUB_FEEDBACK_REPO unset,
every function here returns without attempting a network call, and triage
still completes and stores its result.

The token is a fine-grained PAT scoped to issues on one repository. Nothing
here touches a repo-contents endpoint, and no URL supplied by the triage model
is ever fetched — the repo comes from settings, and issue numbers are used
only as integers against that repo.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import httpx

from .config import Settings
from .triage import (
    MAX_ANALYSIS,
    MAX_SUGGESTION_LEN,
    MAX_SUMMARY,
    sanitise_for_issue,
)

if TYPE_CHECKING:
    from .feedback import Feedback
    from .triage import TriageResult

log = logging.getLogger("app.github")

API_ROOT = "https://api.github.com"
MAX_BODY = 12000


def is_configured(settings: Settings) -> bool:
    return bool(settings.github_feedback_token and settings.github_feedback_repo)


def _headers(settings: Settings) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.github_feedback_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def fetch_recent_open_issues(
    settings: Settings, limit: int = 30
) -> list[dict[str, Any]]:
    """Recent open issues, for duplicate detection. Empty when unconfigured."""
    if not is_configured(settings):
        return []
    url = f"{API_ROOT}/repos/{settings.github_feedback_repo}/issues"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                url,
                headers=_headers(settings),
                params={"state": "open", "per_page": limit, "sort": "created"},
            )
        if resp.status_code >= 400:
            log.warning("GitHub issue list failed: %s %s", resp.status_code, resp.text[:200])
            return []
        # Pull requests come back on this endpoint too; they are not issues.
        return [
            {"number": i["number"], "title": i["title"]}
            for i in resp.json()
            if "pull_request" not in i
        ]
    except httpx.HTTPError as e:
        log.warning("GitHub issue list unreachable: %s", e)
        return []


def build_issue_body(feedback: "Feedback", triage: "TriageResult") -> str:
    """
    Assemble the issue body.

    Every field is sanitised and truncated here regardless of what the model
    returned. The caps are ours: a model that returns a 50k-character
    'summary' produces a truncated one, not a 50k-character issue.
    """
    email = None
    suggestions = "\n".join(
        f"- {sanitise_for_issue(s, email, MAX_SUGGESTION_LEN)}"
        for s in triage.suggested_investigation
    ) or "_none suggested_"
    components = ", ".join(f"`{c}`" for c in triage.affected_components) or "_unknown_"

    body = (
        f"**Severity:** {triage.severity}  \n"
        f"**Category:** {sanitise_for_issue(triage.category, email, 64)}  \n"
        f"**Components:** {components}\n\n"
        f"## Analysis\n\n"
        f"{sanitise_for_issue(triage.reproduction_analysis, email, MAX_ANALYSIS)}\n\n"
        f"## Suggested investigation\n\n{suggestions}\n\n"
        f"## Original report\n\n"
        f"**Kind:** {feedback.kind}  \n"
        f"**Title:** {sanitise_for_issue(feedback.title, email, MAX_SUMMARY)}\n\n"
        f"{sanitise_for_issue(feedback.description, email, 4000)}\n\n"
        f"---\n"
        f"_Filed automatically by feedback triage. The classification above is "
        f"model-generated and unverified. Feedback id `{feedback.id}`._\n"
    )
    return body[:MAX_BODY]


def build_labels(feedback: "Feedback", triage: "TriageResult") -> list[str]:
    """
    Labels are constructed server-side from validated enums only.

    The model never supplies a label string: it chose a severity from a fixed
    set, and that is all that reaches this list.
    """
    labels = [feedback.kind, f"severity:{triage.severity}", "ai-triaged"]
    if triage.severity == "critical":
        labels.append("needs-human")
    return labels


async def file_or_comment(
    settings: Settings, *, feedback: "Feedback", triage: "TriageResult"
) -> str | None:
    """
    Open an issue, or comment on the duplicate the model identified.

    Returns the issue URL, or None when unconfigured or on failure — triage is
    already stored by then, so a GitHub outage costs the classification
    nothing.
    """
    if not is_configured(settings):
        log.info(
            "GitHub not configured; feedback %s triaged but not filed", feedback.id
        )
        return None

    repo = settings.github_feedback_repo
    body = build_issue_body(feedback, triage)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if triage.duplicate_of:
                # Comment on the existing issue instead of opening a new one.
                # The number is an int against the configured repo; no
                # model-supplied URL is ever fetched.
                resp = await client.post(
                    f"{API_ROOT}/repos/{repo}/issues/{int(triage.duplicate_of)}/comments",
                    headers=_headers(settings),
                    json={"body": f"Additional report of this issue:\n\n{body}"},
                )
            else:
                resp = await client.post(
                    f"{API_ROOT}/repos/{repo}/issues",
                    headers=_headers(settings),
                    json={
                        "title": f"[triage] {sanitise_for_issue(triage.summary, None, MAX_SUMMARY)}",
                        "body": body,
                        "labels": build_labels(feedback, triage),
                    },
                )
        if resp.status_code >= 400:
            log.error(
                "GitHub filing failed for feedback %s: %s %s",
                feedback.id,
                resp.status_code,
                resp.text[:300],
            )
            return None
        return resp.json().get("html_url")
    except httpx.HTTPError as e:
        log.error("GitHub unreachable filing feedback %s: %s", feedback.id, e)
        return None
