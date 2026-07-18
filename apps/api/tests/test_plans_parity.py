"""
The marketing site's plan numbers must match the API's.

apps/web is TypeScript and statically rendered, so it cannot import the
Python settings — the numbers are necessarily written twice. This asserts the
two agree, in the same spirit as the prompt single-source guard.

Deliberate limitation, accepted when this was designed: it compares against
the Settings *defaults*, since those are the contract the pricing page is
advertising. A production env override of PRO_ANALYSES_PER_MONTH would drift
past this check. If we ever override in production, the answer is a public
GET /v1/plans that the page reads, not a louder version of this test.
"""

import re
from pathlib import Path

import pytest

from app.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[3]
PLANS_TS = REPO_ROOT / "apps" / "web" / "src" / "lib" / "plans.ts"

# TypeScript constant -> the Settings field it must mirror.
MIRRORED = {
    "analysesPerMonth": "pro_analyses_per_month",
    "creditPackSize": "credit_pack_size",
    "maxFramesPerSession": "pro_max_frames_per_session",
}


def _ts_number(source: str, name: str) -> int:
    match = re.search(rf"\b{name}\s*:\s*(\d+)", source)
    assert match, f"{name} not found in plans.ts"
    return int(match.group(1))


def _default(field: str):
    return Settings.model_fields[field].default


def test_plans_module_exists():
    assert PLANS_TS.is_file(), (
        f"{PLANS_TS} is missing — the pricing page must read its numbers from "
        "a single constants module, not hardcoded strings"
    )


@pytest.mark.parametrize("ts_name,settings_field", sorted(MIRRORED.items()))
def test_web_constant_matches_api_default(ts_name, settings_field):
    source = PLANS_TS.read_text(encoding="utf-8")
    assert _ts_number(source, ts_name) == _default(settings_field), (
        f"plans.ts {ts_name} disagrees with Settings.{settings_field} "
        f"({_default(settings_field)}); the pricing page would advertise a "
        "plan the API does not enforce"
    )


def test_pricing_page_does_not_hardcode_the_numbers():
    """The page must render from the constants, not restate them."""
    page = (
        REPO_ROOT / "apps" / "web" / "src" / "app" / "pricing" / "page.tsx"
    ).read_text(encoding="utf-8")

    assert "plans" in page.lower(), "pricing page does not import the plan constants"

    stale = re.search(r"\b300 analysis minutes\b", page)
    assert not stale, (
        "pricing page still advertises the old minutes-denominated plan"
    )
