"""Offline unit tests for the Open Legal Data client - feature 004.

Uses local fixtures only (no network), captured live on 2026-07-08:
- ``oldp_cases_search_sample.json``  - GET /api/cases/?court__slug=bverwg&page_size=2
- ``oldp_cases_fulltext_sample.json`` - GET /api/cases/search/?text=Mietminderung
- ``oldp_case_detail_sample.json``    - GET /api/cases/521203/
"""

from __future__ import annotations

import json
from pathlib import Path

from de_eli_mcp.citations import enrich_oldp_case, oldp_human_readable_citation
from de_eli_mcp.oldp_client import DEFAULT_BASE_URL, normalize_case_item

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_normalize_metadata_search_item_court_object():
    data = _load("oldp_cases_search_sample.json")
    assert data["count"] > 0
    item = normalize_case_item(data["results"][0])
    assert item["court_name"] == "Bundesverwaltungsgericht"
    assert item["court_slug"] == "bverwg"
    assert item["file_number"]
    assert item["slug"]
    assert item["snippets"] is None


def test_normalize_fulltext_search_item_court_string_and_snippets():
    data = _load("oldp_cases_fulltext_sample.json")
    item = normalize_case_item(data["results"][0])
    assert item["court_name"] == "OLGSL"  # search shape carries a short code string
    assert item["court_slug"] is None
    assert item["snippets"], "full-text search items must surface highlight snippets"
    assert any("Mietminderung" in s for s in item["snippets"])


def test_normalize_detail_has_no_content_leak():
    """normalize_case_item extracts metadata; content stays on the raw payload."""
    raw = _load("oldp_case_detail_sample.json")
    item = normalize_case_item(raw)
    assert "content" not in item
    assert raw["content"], "detail fixture must carry full decision text"
    assert item["file_number"] == "8 O 4860/25"
    assert item["decision_type"] == "Endurteil"


def test_empty_ecli_normalised_to_none():
    raw = _load("oldp_case_detail_sample.json")
    assert raw["ecli"] == ""  # upstream serves empty string
    item = normalize_case_item(raw)
    assert item["ecli"] is None


def test_oldp_human_readable_citation_german_convention():
    item = normalize_case_item(_load("oldp_case_detail_sample.json"))
    citation = oldp_human_readable_citation(item)
    assert citation is not None
    assert "Landgericht" in citation
    assert "vom 21.05.2026" in citation
    assert "8 O 4860/25" in citation


def test_enrich_oldp_case_without_ecli_uses_oldp_uri_and_case_page():
    item = normalize_case_item(_load("oldp_case_detail_sample.json"))
    enriched = enrich_oldp_case(item, base_url=DEFAULT_BASE_URL)
    assert enriched["eli_uri"] == "oldp:case/lg-nurnberg-furth-2026-05-21-8-o-486025"
    assert enriched["source_url"] == (
        f"{DEFAULT_BASE_URL}/case/lg-nurnberg-furth-2026-05-21-8-o-486025/"
    )
    assert enriched["human_readable_citation"] is not None


def test_enrich_oldp_case_prefers_ecli_when_present():
    item = normalize_case_item(_load("oldp_case_detail_sample.json"))
    item["ecli"] = "ECLI:DE:BVERWG:2019:180919U1C46.19.0"
    enriched = enrich_oldp_case(item, base_url=DEFAULT_BASE_URL)
    assert enriched["eli_uri"] == "ECLI:DE:BVERWG:2019:180919U1C46.19.0"
