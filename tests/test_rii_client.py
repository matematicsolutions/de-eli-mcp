"""Offline unit tests for the RII (rechtsprechung-im-internet.de) client - feature 003.

Uses local fixtures only (no network): a hand-picked TOC subset and two real decision
XMLs (one BGH, one BVerfG) captured 2026-07-07. Mirrors the offline/live split used by
NeuRIS tests (test_instructions_drift.py offline, test_smoke.py live).
"""

from __future__ import annotations

from pathlib import Path

from de_eli_mcp.citations import enrich_rii_decision, rii_human_readable_citation
from de_eli_mcp.rii_client import SUPPORTED_COURTS, parse_decision_xml, parse_toc, search_toc

FIXTURES = Path(__file__).parent / "fixtures"


def _load_toc():
    xml_bytes = (FIXTURES / "rii_toc_sample.xml").read_bytes()
    return parse_toc(xml_bytes)


def test_parse_toc_extracts_all_rows():
    items = _load_toc()
    assert len(items) == 8, f"expected 8 rows in the fixture TOC, got {len(items)}"


def test_parse_toc_court_type_is_first_token():
    items = _load_toc()
    court_types = {it.court_type for it in items}
    assert court_types == {"BVerfG", "BGH", "BVerwG", "BAG", "BFH", "BSG", "BPatG"}


def test_supported_courts_matches_fixture_courts():
    items = _load_toc()
    court_types = {it.court_type for it in items}
    unsupported = court_types - SUPPORTED_COURTS
    assert court_types <= SUPPORTED_COURTS, f"unsupported court types: {unsupported}"
    # All six target courts from the task must be present.
    for court in ("BVerfG", "BGH", "BAG", "BFH", "BVerwG", "BSG"):
        assert court in court_types, f"missing target court in fixture: {court}"


def test_doc_id_strips_jb_prefix_and_zip_suffix():
    items = _load_toc()
    bgh = next(it for it in items if it.aktenzeichen == "IX ZB 72/08")
    assert bgh.doc_id == "JURE100055033", f"doc_id = {bgh.doc_id!r}"


def test_search_toc_filters_by_court():
    items = _load_toc()
    total, page = search_toc(items, court="BVerfG")
    assert total == 1
    assert page[0].court_type == "BVerfG"


def test_search_toc_filters_by_aktenzeichen_substring_case_insensitive():
    items = _load_toc()
    total, page = search_toc(items, aktenzeichen_contains="ix zb")
    assert total == 1
    assert page[0].aktenzeichen == "IX ZB 72/08"


def test_search_toc_filters_by_date_range():
    items = _load_toc()
    total, page = search_toc(items, date_from="2024-01-01", date_to="2024-12-31")
    assert total == 2  # BVerfG (20240702) + BAG (20240620)
    dates = {it.decision_date for it in page}
    assert dates == {"20240702", "20240620"}


def test_search_toc_sorts_newest_first_and_paginates():
    items = _load_toc()
    total, page = search_toc(items, limit=2, offset=0)
    assert total == 8
    assert len(page) == 2
    assert page[0].decision_date >= page[1].decision_date


def test_search_toc_no_match_returns_empty():
    items = _load_toc()
    total, page = search_toc(items, court="BGH", aktenzeichen_contains="nonexistent-xyz")
    assert total == 0
    assert page == []


def test_parse_decision_xml_bgh_sample():
    xml_bytes = (FIXTURES / "rii_bgh_sample.xml").read_bytes()
    doc = parse_decision_xml(xml_bytes)
    assert doc["doknr"] == "JURE100055033"
    assert doc["gertyp"] == "BGH"
    assert doc["spruchkoerper"] == "9. Zivilsenat"
    assert doc["entsch_datum"] == "20100114"
    assert doc["aktenzeichen"] == "IX ZB 72/08"
    assert doc["doktyp"] == "Beschluss"
    assert doc["ecli"] is None  # this BGH sample predates ECLI assignment
    assert doc["full_text"] is not None and "Insolvenzverfahren" in doc["full_text"]
    assert doc["identifier"] is not None and doc["identifier"].startswith("http")


def test_parse_decision_xml_bverfg_sample_has_ecli():
    xml_bytes = (FIXTURES / "rii_bverfg_sample.xml").read_bytes()
    doc = parse_decision_xml(xml_bytes)
    assert doc["gertyp"] == "BVerfG"
    assert doc["ecli"] == "ECLI:DE:BVerfG:2024:rk20241120.1bvr226823"
    assert doc["aktenzeichen"] == "1 BvR 2268/23"
    assert doc["full_text"] is not None and len(doc["full_text"]) > 0


def test_rii_human_readable_citation_bverfg():
    xml_bytes = (FIXTURES / "rii_bverfg_sample.xml").read_bytes()
    doc = parse_decision_xml(xml_bytes)
    citation = rii_human_readable_citation(doc)
    assert citation is not None
    assert "BVerfG" in citation
    assert "20.11.2024" in citation
    assert "1 BvR 2268/23" in citation


def test_rii_human_readable_citation_bgh_no_doktyp_missing_is_tolerated():
    xml_bytes = (FIXTURES / "rii_bgh_sample.xml").read_bytes()
    doc = parse_decision_xml(xml_bytes)
    citation = rii_human_readable_citation(doc)
    assert citation is not None
    assert "BGH" in citation
    assert "IX ZB 72/08" in citation


def test_enrich_rii_decision_uses_ecli_as_eli_uri_when_present():
    xml_bytes = (FIXTURES / "rii_bverfg_sample.xml").read_bytes()
    doc = parse_decision_xml(xml_bytes)
    enriched = enrich_rii_decision(doc)
    assert enriched["eli_uri"] == "ECLI:DE:BVerfG:2024:rk20241120.1bvr226823"
    assert enriched["source_url"].startswith("http")
    assert enriched["human_readable_citation"] is not None


def test_enrich_rii_decision_falls_back_to_rii_uri_without_ecli():
    xml_bytes = (FIXTURES / "rii_bgh_sample.xml").read_bytes()
    doc = parse_decision_xml(xml_bytes)
    enriched = enrich_rii_decision(doc)
    assert enriched["eli_uri"] == "rii:JURE100055033"
