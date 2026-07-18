"""Smoke tests - require internet, not run in offline CI.

Run manually:

    pytest tests/test_smoke.py -v

All tests go through the live NeuRIS API - a deliberate POC choice.
Snapshot testing arrives in v1.0 (TODO).
"""

from __future__ import annotations

import pytest

from de_eli_mcp.models import (
    CaseSearchQuery,
    DipSearchQuery,
    OldpCaseQuery,
    RiiCaseQuery,
    SearchQuery,
)
from de_eli_mcp.server import (
    de_case_search,
    de_dip_get_document,
    de_dip_search,
    de_get_act,
    de_get_decision,
    de_get_decision_text,
    de_get_text,
    de_list_publishers,
    de_oldp_case_search,
    de_oldp_get_case,
    de_rii_case_search,
    de_rii_get_case_text,
    de_search,
)


# The point-in-time segment of an expression-level ELI moves every time the act
# is amended: NeuRIS served the BDSG as .../2017/s2097/2025-01-01/1/deu until an
# amendment shifted it to .../2017/s2097/2026-07-10/1/deu, which silently broke
# these two tests. Hard-coding a dated ELI therefore guarantees a red suite on
# the next amendment, and that red says nothing about our code. Resolve the
# current expression from search instead, and assert against what we resolved.
async def resolve_bdsg_eli() -> str:
    """Return the ELI of the BDSG expression NeuRIS currently serves."""
    result = await de_search(SearchQuery(search_term="BDSG", size=10))
    for item in result.items:
        if (item.abbreviation or "").upper() == "BDSG" and item.eli_uri:
            return item.eli_uri
    pytest.skip("NeuRIS returned no BDSG entry - upstream data gap, not our bug")


# A stable BAG data-protection decision document number.
BAG_DECISION = "KARE600069049"


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
    bdsg_eli = await resolve_bdsg_eli()
    act = await de_get_act(bdsg_eli)
    assert act.eli_uri == bdsg_eli, f"eli_uri = {act.eli_uri!r}"
    assert act.abbreviation == "BDSG", f"abbreviation = {act.abbreviation!r}"
    assert act.human_readable_citation is not None
    assert "BDSG" in act.human_readable_citation
    assert act.source_url is not None and act.source_url.startswith("https://")


@pytest.mark.asyncio
async def test_smoke_get_text_html() -> None:
    bdsg_eli = await resolve_bdsg_eli()
    text = await de_get_text(bdsg_eli, format="html")
    assert text.eli_uri == bdsg_eli
    assert text.format == "html"
    assert text.content is not None and len(text.content) > 0
    assert text.source_url.startswith("https://")
    assert text.byte_size and text.byte_size > 0


@pytest.mark.asyncio
async def test_smoke_case_search() -> None:
    result = await de_case_search(CaseSearchQuery(search_term="Datenschutz", size=5))
    assert result.total_items > 0, "Expected case-law hits for 'Datenschutz'"
    assert len(result.items) > 0
    for item in result.items:
        # NeuRIS beta drops `ecli` for some decisions it previously served with one
        # (documented in README - KARE600069049 is the live example); when present
        # it must be well-formed.
        if item.ecli is not None:
            assert item.ecli.startswith("ECLI:DE:"), f"bad ecli: {item.ecli!r}"
        assert item.human_readable_citation is not None
        assert item.source_url is not None


@pytest.mark.asyncio
async def test_smoke_get_decision() -> None:
    decision = await de_get_decision(BAG_DECISION)
    # NeuRIS beta has been observed serving this decision both with and without its
    # ECLI (ECLI:DE:BAG:2024:...) - RII serves it with the full ECLI either way.
    if decision.ecli is not None:
        assert decision.ecli.startswith("ECLI:DE:BAG:")
    assert decision.human_readable_citation is not None
    assert "BAG" in decision.human_readable_citation
    assert decision.source_url is not None and decision.source_url.startswith("https://")


@pytest.mark.asyncio
async def test_smoke_get_decision_text_html() -> None:
    text = await de_get_decision_text(BAG_DECISION, format="html")
    assert text.format == "html"
    assert text.content is not None and len(text.content) > 0
    assert text.source_url.startswith("https://")
    assert text.byte_size and text.byte_size > 0


# --- RII (rechtsprechung-im-internet.de) smoke tests --------------------------
# These hit the live ~23 MB rii-toc.xml (cached client-side after the first call
# within a test session/process) and one live decision ZIP per court.


@pytest.mark.asyncio
async def test_smoke_rii_case_search_bverfg() -> None:
    result = await de_rii_case_search(RiiCaseQuery(court="BVerfG", limit=5))
    assert result.total_items > 0, "Expected BVerfG hits in the live RII TOC"
    assert len(result.items) > 0
    for item in result.items:
        assert item.court_type == "BVerfG"
        assert item.doc_id, f"missing doc_id in {item}"
        assert item.zip_url.startswith("http")


@pytest.mark.asyncio
async def test_smoke_rii_case_search_each_target_court_has_hits() -> None:
    """All six courts named in the task (BVerfG/BGH/BAG/BFH/BVerwG/BSG) must be
    non-empty in the live RII TOC - this is the whole point of the connector."""
    for court in ("BVerfG", "BGH", "BAG", "BFH", "BVerwG", "BSG"):
        result = await de_rii_case_search(RiiCaseQuery(court=court, limit=1))
        assert result.total_items > 0, f"Expected at least one {court} decision in live RII"


@pytest.mark.asyncio
async def test_smoke_rii_get_case_text_bverfg() -> None:
    search = await de_rii_case_search(RiiCaseQuery(court="BVerfG", limit=1))
    assert search.items, "Need at least one BVerfG hit to fetch full text"
    doc_id = search.items[0].doc_id

    text = await de_rii_get_case_text(doc_id)
    assert text.doc_id == doc_id
    assert text.eli_uri, "missing eli_uri"
    assert text.court == "BVerfG"
    assert text.human_readable_citation is not None
    assert "BVerfG" in text.human_readable_citation
    assert text.source_url.startswith("http")
    assert text.content is not None and len(text.content) > 0
    assert text.byte_size and text.byte_size > 0


# --- Open Legal Data (de.openlegaldata.io) smoke tests - feature 004 -----------


@pytest.mark.asyncio
async def test_smoke_oldp_metadata_filter_narrows() -> None:
    """court__slug must genuinely narrow the result set (guards against the
    silent-no-op filter failure mode: date__gte returns the unfiltered total)."""
    unfiltered = await de_oldp_case_search(OldpCaseQuery())
    filtered = await de_oldp_case_search(OldpCaseQuery(court_slug="bverwg"))
    assert unfiltered.total_items > 100_000, "OLDP total unexpectedly small"
    assert 0 < filtered.total_items < unfiltered.total_items
    for item in filtered.items:
        assert item.court_slug == "bverwg"
        assert item.human_readable_citation is not None
        assert item.source_url is not None and item.source_url.startswith("https://")


@pytest.mark.asyncio
async def test_smoke_oldp_fulltext_search_returns_snippets() -> None:
    result = await de_oldp_case_search(OldpCaseQuery(text="Mietminderung"))
    assert result.total_items > 0
    assert result.items
    assert any(item.snippets for item in result.items), "expected highlight snippets"


@pytest.mark.asyncio
async def test_smoke_oldp_get_case_full_text() -> None:
    search = await de_oldp_case_search(OldpCaseQuery(court_slug="bverwg"))
    assert search.items, "Need at least one BVerwG hit in OLDP"
    ref = str(search.items[0].id)

    case = await de_oldp_get_case(ref)
    assert case.eli_uri, "missing eli_uri"
    assert case.human_readable_citation is not None
    assert case.source_url.startswith("https://")
    assert case.content is not None and len(case.content) > 0
    assert case.byte_size and case.byte_size > 0


# --- Bundestag DIP smoke tests - feature 004 ------------------------------------


@pytest.mark.asyncio
async def test_smoke_dip_search_exact_dokumentnummer() -> None:
    result = await de_dip_search(
        DipSearchQuery(resource="drucksache", dokumentnummer="20/1", zuordnung="BT")
    )
    assert result.total_items == 1, (
        f"expected exactly 1 hit for BT-Drs. 20/1, got {result.total_items}"
    )
    item = result.items[0]
    assert item.human_readable_citation == "BT-Drs. 20/1"
    assert item.source_url is not None and item.source_url.endswith(".pdf")


@pytest.mark.asyncio
async def test_smoke_dip_titel_filter_narrows() -> None:
    unfiltered = await de_dip_search(DipSearchQuery(resource="drucksache"))
    filtered = await de_dip_search(DipSearchQuery(resource="drucksache", titel="Datenschutz"))
    assert unfiltered.total_items > 100_000, "DIP drucksache total unexpectedly small"
    assert 0 < filtered.total_items < unfiltered.total_items


@pytest.mark.asyncio
async def test_smoke_dip_get_document_text() -> None:
    search = await de_dip_search(
        DipSearchQuery(resource="drucksache", dokumentnummer="20/1", zuordnung="BT")
    )
    assert search.items
    doc_id = search.items[0].id
    assert doc_id

    doc = await de_dip_get_document("drucksache-text", doc_id)
    assert doc.human_readable_citation == "BT-Drs. 20/1"
    assert doc.source_url.startswith("https://")
    assert doc.content is not None and len(doc.content) > 1000
    assert doc.byte_size and doc.byte_size > 0
