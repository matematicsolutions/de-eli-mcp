"""Offline unit tests for the Bundestag DIP client - feature 004.

Uses local fixtures only (no network), captured live on 2026-07-08:
- ``dip_drucksache_search_sample.json`` - /api/v1/drucksache?f.dokumentnummer=20/1&f.zuordnung=BT
- ``dip_drucksache_text_sample.json``   - same query against /api/v1/drucksache-text
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from de_eli_mcp.citations import (
    dip_human_readable_citation,
    dip_source_url,
    enrich_dip_document,
)
from de_eli_mcp.dip_client import SUPPORTED_RESOURCES, DipClient

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_search_fixture_envelope():
    data = _load("dip_drucksache_search_sample.json")
    assert data["numFound"] == 1  # exact dokumentnummer + zuordnung -> exactly one hit
    assert data["cursor"]
    doc = data["documents"][0]
    assert doc["dokumentnummer"] == "20/1"
    assert doc["herausgeber"] == "BT"
    assert doc["dokumentart"] == "Drucksache"


def test_text_fixture_carries_full_text():
    data = _load("dip_drucksache_text_sample.json")
    doc = data["documents"][0]
    assert isinstance(doc["text"], str) and len(doc["text"]) > 1000


def test_dip_citation_bt_drucksache():
    doc = _load("dip_drucksache_search_sample.json")["documents"][0]
    assert dip_human_readable_citation(doc) == "BT-Drs. 20/1"


def test_dip_citation_plenarprotokoll():
    doc = {"herausgeber": "BR", "dokumentart": "Plenarprotokoll", "dokumentnummer": "1051"}
    assert dip_human_readable_citation(doc) == "BR-PlPr 1051"


def test_dip_citation_vorgang_falls_back_to_typ_and_titel():
    doc = {"vorgangstyp": "Gesetzgebung", "titel": "Weitergeltung von Geschäftsordnungsrecht"}
    citation = dip_human_readable_citation(doc)
    assert citation == "Gesetzgebung: Weitergeltung von Geschäftsordnungsrecht"


def test_dip_source_url_prefers_official_pdf():
    doc = _load("dip_drucksache_search_sample.json")["documents"][0]
    url = dip_source_url(doc)
    assert url.startswith("https://dserver.bundestag.de/")
    assert url.endswith(".pdf")


def test_dip_source_url_falls_back_to_portal():
    assert dip_source_url({}) == "https://dip.bundestag.de"


def test_enrich_dip_document_contract_fields():
    doc = _load("dip_drucksache_search_sample.json")["documents"][0]
    enriched = enrich_dip_document(doc)
    assert enriched["eli_uri"] == f"dip:drucksache/{doc['id']}"
    assert enriched["human_readable_citation"] == "BT-Drs. 20/1"
    assert enriched["source_url"].startswith("https://")


def test_supported_resources_are_the_documented_five():
    assert {
        "drucksache",
        "drucksache-text",
        "plenarprotokoll",
        "plenarprotokoll-text",
        "vorgang",
    } == SUPPORTED_RESOURCES


async def test_client_rejects_unknown_resource():
    async with DipClient() as client:
        with pytest.raises(ValueError, match="Unsupported DIP resource"):
            await client.search("aktivitaet")
        with pytest.raises(ValueError, match="Unsupported DIP resource"):
            await client.get_document("person", "1")
