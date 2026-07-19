"""
The worker's dev path must resolve prompts from the canonical package.

Counterpart to apps/api/tests/test_prompt_single_source.py, which enforces
that exactly one definition exists repo-wide. This side asserts the worker
actually reaches it, and that reaching it costs no server dependencies —
the worker ships to desktops and must not carry FastAPI or a provider SDK.
"""

import importlib.util

import reenigne_prompts
from reenigne.analyze import llm_client


def test_worker_dev_path_resolves_the_canonical_object():
    """Identity, not equality — the same dict cannot hold different text."""
    assert llm_client.PROMPTS is reenigne_prompts.PROMPTS


def test_worker_has_no_local_prompt_module():
    """The old duplicate lived here; it must not come back."""
    assert importlib.util.find_spec("reenigne.analyze.prompts") is None


def test_prompts_import_needs_no_server_dependencies():
    """
    Importing the prompts must not require the API's stack. If this starts
    failing, the shared package has grown a dependency and the worker build
    is about to bloat — or break, since the desktop bundle has none of these.
    """
    for module in ("fastapi", "sqlalchemy", "stripe"):
        assert importlib.util.find_spec(module) is None, (
            f"{module} is installed in the worker environment; the worker "
            "should never need the server stack"
        )


def test_triage_prompt_is_not_a_user_selectable_template():
    """The worker validates --prompt against PROMPTS; triage is not one."""
    assert "triage" not in reenigne_prompts.PROMPTS


def test_templates_are_present_and_non_empty():
    assert set(reenigne_prompts.PROMPTS) == {
        "teardown",
        "ux",
        "features",
        "tech-stack",
    }
    for name, text in reenigne_prompts.PROMPTS.items():
        assert isinstance(text, str) and text.strip(), f"{name} is empty"
