"""Smoke tests - require internet, not run in offline CI.

Run manually:

    pytest tests/test_smoke.py -v

All tests go through the live NeuRIS API - a deliberate POC choice.
Snapshot testing arrives in v1.0 (TODO).
"""

from __future__ import annotations

import pytest

from de_eli_mcp.models import SearchQuery
from de_eli_mcp.server import (
    de_get_act,
    de_get_text,
    de_list_publishers,
    de_search,
)

# A stable expression-level ELI: Bundesdatenschutzgesetz (BDSG).
BDSG_ELI = "eli/bund/bgbl-1/2017/s2097/2025-01-01/1/deu"


@pytest.mark.asyncio
async def test_smoke_list_publishers() -> None:
    publishers = await de_list_publishers()
    assert len(publishers) > 0, "The publisher list should be non-empty"
    codes = {p.code for p in publishers}
    assert "bgbl-1" in codes, f"BGBl I (bgbl-1) should be present, got: {codes}"


@pytest.mark.asyncio
async def test_smoke_search_bdsg() -> None:
    result = await de_search(SearchQuery(search_term="Bundesdatenschutzgesetz", size=5))
    assert result.total_items > 0, "Expected hits for 'Bundesdatenschutzgesetz'"
    assert len(result.items) > 0
    # Every item must carry the contract (Art. 4 CONSTITUTION).
    for item in result.items:
        assert item.eli_uri is not None, f"missing eli_uri in {item}"
        assert item.eli_uri.startswith("eli/"), f"unexpected eli_uri: {item.eli_uri!r}"
        assert item.human_readable_citation is not None, f"missing citation in {item}"
        assert item.source_url is not None, f"missing source_url in {item}"


@pytest.mark.asyncio
async def test_smoke_get_bdsg() -> None:
    act = await de_get_act(BDSG_ELI)
    assert act.eli_uri == BDSG_ELI, f"eli_uri = {act.eli_uri!r}"
    assert act.abbreviation == "BDSG", f"abbreviation = {act.abbreviation!r}"
    assert act.human_readable_citation is not None
    assert "BDSG" in act.human_readable_citation
    assert act.source_url is not None and act.source_url.startswith("https://")


@pytest.mark.asyncio
async def test_smoke_get_text_html() -> None:
    text = await de_get_text(BDSG_ELI, format="html")
    assert text.eli_uri == BDSG_ELI
    assert text.format == "html"
    assert text.content is not None and len(text.content) > 0
    assert text.source_url.startswith("https://")
    assert text.byte_size and text.byte_size > 0
