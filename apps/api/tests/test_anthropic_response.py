"""
Reading the text out of an Anthropic response.

content[0].text assumes the first block is text. That holds today and would
break the moment a response leads with a thinking or tool_use block —
crashing in the last line of the adapter, after a slow vision call has already
been paid for.
"""

from types import SimpleNamespace

import pytest

from app.llm import first_text_block


def block(kind: str, **kw):
    return SimpleNamespace(type=kind, **kw)


def test_reads_a_leading_text_block():
    assert first_text_block([block("text", text="hello")]) == "hello"


def test_skips_a_leading_thinking_block():
    blocks = [
        block("thinking", thinking="reasoning..."),
        block("text", text="the report"),
    ]
    assert first_text_block(blocks) == "the report"


def test_skips_a_leading_tool_use_block():
    blocks = [
        block("tool_use", id="t1", name="search", input={}),
        block("text", text="the report"),
    ]
    assert first_text_block(blocks) == "the report"


def test_skips_an_unknown_future_block_type():
    """Forward compatibility: an unrecognised type is skipped, not fatal."""
    blocks = [block("some_future_type", data="?"), block("text", text="ok")]
    assert first_text_block(blocks) == "ok"


def test_returns_the_first_of_several_text_blocks():
    blocks = [block("text", text="first"), block("text", text="second")]
    assert first_text_block(blocks) == "first"


def test_empty_string_text_block_is_returned_not_skipped():
    """An empty completion is a real answer, distinct from having no text."""
    assert first_text_block([block("text", text="")]) == ""


@pytest.mark.parametrize("blocks", [[], None])
def test_no_blocks_raises_a_clear_error(blocks):
    with pytest.raises(RuntimeError, match="no text block"):
        first_text_block(blocks)


def test_error_names_the_block_types_it_did_see():
    """So the log says why, rather than just that it failed."""
    with pytest.raises(RuntimeError) as e:
        first_text_block([block("thinking", thinking="..."), block("tool_use")])
    assert "thinking" in str(e.value)
    assert "tool_use" in str(e.value)


def test_old_behaviour_would_have_crashed_on_a_leading_thinking_block():
    """Pins why this exists: the previous expression raises on this input."""
    blocks = [block("thinking", thinking="..."), block("text", text="ok")]
    with pytest.raises(AttributeError):
        _ = blocks[0].text
    assert first_text_block(blocks) == "ok"
