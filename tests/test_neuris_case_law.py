"""NeuRIS case-law routing - offline guards (no network).

On 2026-10-08 NeuRIS removed ``/v1/case-law`` and ``/v1/case-law/**``: both now answer
HTTP 410 with a body naming the successor (``/v1/rechtsprechung``, same host, same
response shape). The live smoke tests caught it; these guards keep it caught offline:

1. the client asks the successor paths, never the removed ones;
2. a 410 from NeuRIS surfaces as a named ``endpoint_gone`` error that carries the
   upstream's own successor hint and, for the case-law tools, the RII / OLDP
   fallbacks - not as an anonymous ``upstream_error``.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from de_eli_mcp import server
from de_eli_mcp.cache import HttpCache
from de_eli_mcp.client import NeurisClient
from de_eli_mcp.models import CaseSearchQuery

BASE = "https://neuris.invalid"
DECISION = {
    "@id": "/v1/rechtsprechung/KARE600069049",
    "@type": "Decision",
    "documentNumber": "KARE600069049",
    "ecli": "ECLI:DE:BAG:2024:200624.U.8AZR124.23.0",
    "courtType": "BAG",
    "documentType": "Urteil",
    "decisionDate": "2024-06-20",
    "fileNumbers": ["8 AZR 124/23"],
    "encoding": [
        {
            "contentUrl": "/v1/rechtsprechung/KARE600069049.html",
            "encodingFormat": "text/html",
        }
    ],
}
GONE_BODY = {
    "errors": [
        {
            "code": "gone",
            "message": (
                "This endpoint has been removed. Use /v1/rechtsprechung/KARE600069049 instead."
            ),
            "parameter": "/v1/rechtsprechung/KARE600069049",
        }
    ]
}


def _client(tmp_path: Path, handler, seen: list[str]) -> NeurisClient:
    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return handler(request)

    client = NeurisClient(base_url=BASE, cache=HttpCache(tmp_path / "cache"))
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(record))
    return client


def _serve_successor(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.startswith("/v1/case-law"):
        return httpx.Response(410, json=GONE_BODY)
    if path == "/v1/rechtsprechung":
        return httpx.Response(200, json={"totalItems": 1, "member": [{"item": DECISION}]})
    if path == "/v1/rechtsprechung/KARE600069049":
        return httpx.Response(200, json=DECISION)
    if path == "/v1/rechtsprechung/KARE600069049.html":
        return httpx.Response(
            200, text="<html>Urteil</html>", headers={"content-type": "text/html"}
        )
    return httpx.Response(404)


async def test_case_search_uses_rechtsprechung(tmp_path: Path) -> None:
    seen: list[str] = []
    async with _client(tmp_path, _serve_successor, seen) as client:
        raw = await client.case_search({"searchTerm": "Datenschutz", "size": 1})
    assert seen == ["/v1/rechtsprechung"]
    assert raw["totalItems"] == 1


async def test_get_decision_uses_rechtsprechung(tmp_path: Path) -> None:
    seen: list[str] = []
    async with _client(tmp_path, _serve_successor, seen) as client:
        raw = await client.get_decision("KARE600069049")
    assert seen == ["/v1/rechtsprechung/KARE600069049"]
    assert raw["documentNumber"] == "KARE600069049"


def _gone(request: httpx.Request) -> httpx.Response:
    return httpx.Response(410, json=GONE_BODY)


@pytest.fixture
def neuris_gone(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[str]:
    """Route every NeuRIS call in the server to a transport that answers 410."""
    seen: list[str] = []
    monkeypatch.setenv("DE_ELI_AUDIT_DIR", str(tmp_path / "audit"))
    monkeypatch.setattr(server, "NeurisClient", lambda base_url: _client(tmp_path, _gone, seen))
    return seen


def _assert_endpoint_gone_with_fallbacks(err: server.ELIError) -> None:
    assert err.code == "endpoint_gone"
    msg = str(err)
    assert msg.startswith("[endpoint_gone]")
    assert "/v1/rechtsprechung/KARE600069049" in msg  # upstream's own successor hint
    assert "de_rii_case_search" in msg  # federal courts
    assert "de_oldp_case_search" in msg  # state courts


async def test_case_search_410_is_endpoint_gone(neuris_gone: list[str]) -> None:
    with pytest.raises(server.ELIError) as exc:
        await server.de_case_search(CaseSearchQuery(search_term="Datenschutz"))
    _assert_endpoint_gone_with_fallbacks(exc.value)
    assert neuris_gone, "the tool never reached the transport"


async def test_get_decision_410_is_endpoint_gone(neuris_gone: list[str]) -> None:
    with pytest.raises(server.ELIError) as exc:
        await server.de_get_decision("KARE600069049")
    _assert_endpoint_gone_with_fallbacks(exc.value)


async def test_get_decision_text_410_is_endpoint_gone(neuris_gone: list[str]) -> None:
    with pytest.raises(server.ELIError) as exc:
        await server.de_get_decision_text("KARE600069049", format="html")
    _assert_endpoint_gone_with_fallbacks(exc.value)


def test_410_on_legislation_has_no_case_law_fallback() -> None:
    """The fallback names case-law tools only where they apply."""
    req = httpx.Request("GET", f"{BASE}/v1/legislation")
    exc = httpx.HTTPStatusError(
        "gone", request=req, response=httpx.Response(410, json=GONE_BODY, request=req)
    )
    err = server._map_http_error(exc)
    assert isinstance(err, server.ELIError) and err.code == "endpoint_gone"
    assert "de_rii_case_search" not in str(err)


def test_410_without_json_body_still_named() -> None:
    req = httpx.Request("GET", f"{BASE}/v1/case-law")
    exc = httpx.HTTPStatusError(
        "gone", request=req, response=httpx.Response(410, text="Gone", request=req)
    )
    err = server._map_http_error(exc)
    assert isinstance(err, server.ELIError) and err.code == "endpoint_gone"
