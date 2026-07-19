"""
The prompts must have exactly one definition, shared by both consumers.

Prompts are the product. If the paid server path and the worker's local dev
path can resolve different text for the same template name, a report generated
in dev is not the report the customer receives — and the divergence is silent,
because both sides keep working.

These checks are structural rather than a string comparison between two
copies: a string comparison only proves the copies agree *today*, whereas
asserting a single definition site plus object identity from each consumer
makes divergence impossible by construction.

No FastAPI or provider SDK is needed for any of this, so the same guarantees
hold in the worker's suite (see packages/worker/tests/test_prompt_source.py).
"""

import ast
from pathlib import Path

import pytest

import reenigne_prompts

REPO_ROOT = Path(__file__).resolve().parents[3]
CANONICAL = REPO_ROOT / "apps" / "api" / "reenigne_prompts" / "__init__.py"

# Every consumer that resolves prompt text, and the module each must take it
# from. Add to this list when a new consumer appears.
CONSUMERS = [
    REPO_ROOT / "apps" / "api" / "app" / "llm.py",
    REPO_ROOT / "packages" / "worker" / "src" / "reenigne" / "analyze" / "llm_client.py",
]

TEMPLATE_NAMES = {"teardown", "ux", "features", "tech-stack"}

_SKIP_DIRS = {
    ".venv", "venv", "node_modules", "__pycache__", ".git",
    ".next", "dist", "dist-electron", "build", ".pytest_cache",
}


def _python_files():
    for path in REPO_ROOT.rglob("*.py"):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        yield path


def _defines_prompts(path: Path) -> bool:
    """True if this module assigns a module-level PROMPTS mapping."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return False
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "PROMPTS":
                    # An import re-export binds a Name, not a literal dict.
                    if isinstance(node.value, ast.Dict):
                        return True
    return False


def test_repo_root_is_discoverable():
    """Guard the path math — a wrong root would make everything below vacuous."""
    assert CANONICAL.is_file(), CANONICAL
    assert (REPO_ROOT / "packages" / "worker").is_dir()
    assert len(list(_python_files())) > 20


def test_exactly_one_module_defines_the_prompts():
    definers = sorted(p for p in _python_files() if _defines_prompts(p))
    assert definers == [CANONICAL], (
        "prompt templates must be defined in exactly one place; found "
        f"{[str(p.relative_to(REPO_ROOT)) for p in definers]}"
    )


@pytest.mark.parametrize("consumer", CONSUMERS, ids=lambda p: p.name)
def test_consumers_import_from_the_canonical_module(consumer):
    """
    Each consumer must take PROMPTS from reenigne_prompts, not define or
    re-derive it. This is what would fail if someone reintroduced a local copy
    in either package.
    """
    assert consumer.is_file(), consumer
    tree = ast.parse(consumer.read_text(encoding="utf-8"))

    sources = [
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and any(alias.name == "PROMPTS" for alias in node.names)
    ]
    assert sources == ["reenigne_prompts"], (
        f"{consumer.name} resolves PROMPTS from {sources or 'nowhere'}; "
        "it must import from the canonical reenigne_prompts package"
    )


def test_api_consumer_resolves_the_canonical_object():
    """Identity, not equality — the same dict cannot hold different text."""
    from app import llm

    assert llm.PROMPTS is reenigne_prompts.PROMPTS


def test_canonical_module_exposes_the_expected_templates():
    assert set(reenigne_prompts.PROMPTS) == TEMPLATE_NAMES
    for name, text in reenigne_prompts.PROMPTS.items():
        assert isinstance(text, str) and text.strip(), f"{name} is empty"


def test_triage_prompt_is_exported_but_not_user_selectable():
    """
    PROMPTS is the allowlist /v1/analyze/jobs validates prompt_template
    against. TRIAGE_PROMPT is an internal classifier; admitting it to that
    dict would let a caller run it as an analysis template.
    """
    assert reenigne_prompts.TRIAGE_PROMPT.strip()
    assert "triage" not in reenigne_prompts.PROMPTS
    assert reenigne_prompts.TRIAGE_PROMPT not in reenigne_prompts.PROMPTS.values()


def test_canonical_package_has_no_third_party_imports():
    """
    The worker must be able to import this without FastAPI, SQLAlchemy or a
    provider SDK. Keeping it import-free is what makes that true.
    """
    tree = ast.parse(CANONICAL.read_text(encoding="utf-8"))
    imported = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    assert not imported, (
        "reenigne_prompts must stay dependency-free so the worker can install "
        "it standalone"
    )
