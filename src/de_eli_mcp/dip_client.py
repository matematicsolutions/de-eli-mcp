"""Async client for the Bundestag DIP API (search.dip.bundestag.de) - feature 004.

DIP (Dokumentations- und Informationssystem fuer Parlamentsmaterialien) is the German
parliament's official documentation system: Drucksachen (bills, motions, reports,
government answers), Plenarprotokolle (plenary transcripts), Vorgaenge (legislative
procedures) and more, for Bundestag AND Bundesrat. Legislative history is legally
weighty in Germany - Gesetzesbegruendungen from Drucksachen are a standard aid of
statutory interpretation.

Live totals at check (2026-07-08): drucksache 287 327 (full text available),
plenarprotokoll 5 789, vorgang 334 524, vorgangsposition 691 937,
aktivitaet 1 763 478, person 5 622.

API: documented RESTful service at ``https://search.dip.bundestag.de/api/v1``
(Swagger UI + OpenAPI YAML at the same base). An API key is required; the Bundestag
publishes a PUBLIC key on https://dip.bundestag.de/über-dip/hilfe/api - the current one
is valid until end of May 2027 and is embedded below as the default. It rotates roughly
yearly; override with ``DE_DIP_API_KEY`` when it expires (or with your own key, which
the Bundestag grants on request for 10 years). Filters are ``f.*`` query parameters
(``f.titel``, ``f.dokumentnummer``, ``f.datum.start``/``end``, ``f.zuordnung``,
``f.wahlperiode``, ...); pagination is cursor-based; totals come from ``numFound``.

Verified live 2026-07-08: ``f.titel=Datenschutz`` narrows 287 327 -> 424;
``f.dokumentnummer=20/1`` + ``f.zuordnung=BT`` -> exactly 1; ``drucksache-text``
returns the same envelope plus a ``text`` field with the full document text.
"""

from __future__ import annotations

from typing import Any

import anyio
import httpx

from .cache import HttpCache

DEFAULT_BASE_URL = "https://search.dip.bundestag.de"

# The PUBLIC API key the Bundestag documents at
# https://dip.bundestag.de/über-dip/hilfe/api ("Der zunaechst bis Ende Mai 2027
# gueltige API-Key lautet: ..."). Not a secret - published by the operator for
# general use. Rotates ~yearly; override via DE_DIP_API_KEY.
PUBLIC_API_KEY = "R2BZaee.DjdCyihKZMf8AOjtScubP2EVydegzjmBIQ"

DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
USER_AGENT = "de-eli-mcp/0.3.0 (+https://github.com/matematicsolutions/de-eli-mcp)"

_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3

_SEARCH_TTL_SECONDS = 15 * 60
_DOCUMENT_TTL_SECONDS = 24 * 60 * 60

# Resource types exposed by our tools. The API also serves aktivitaet / person /
# vorgangsposition; kept out of the tool surface to stay focused on documents.
SUPPORTED_RESOURCES = frozenset(
    {"drucksache", "drucksache-text", "plenarprotokoll", "plenarprotokoll-text", "vorgang"}
)


class DipClient:
    """Async client for the Bundestag DIP API. Use as ``async with DipClient() as c:``."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str = PUBLIC_API_KEY,
        cache: HttpCache | None = None,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._cache = cache or HttpCache()
        self._http = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Authorization": f"ApiKey {api_key}",
            },
            follow_redirects=True,
        )

    async def __aenter__(self) -> DipClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()
        self._cache.close()

    async def _get_json_with_backoff(
        self, url: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                resp = await self._http.get(url, params=params)
                resp.raise_for_status()
                data: dict[str, Any] = resp.json()
                return data
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if exc.response.status_code not in _RETRY_STATUS or attempt == _MAX_ATTEMPTS - 1:
                    raise
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt == _MAX_ATTEMPTS - 1:
                    raise
            await anyio.sleep(0.5 * (2**attempt))
        assert last_exc is not None
        raise last_exc

    async def search(
        self,
        resource: str,
        *,
        titel: str | None = None,
        dokumentnummer: str | None = None,
        zuordnung: str | None = None,
        wahlperiode: int | None = None,
        vorgangstyp: str | None = None,
        date_start: str | None = None,
        date_end: str | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """Search one DIP resource type. Returns the raw envelope
        ``{numFound, documents, cursor}``. Pass the returned ``cursor`` back in to
        page; the API signals the end when the cursor stops changing.
        """
        if resource not in SUPPORTED_RESOURCES:
            raise ValueError(
                f"Unsupported DIP resource {resource!r}. Supported: {sorted(SUPPORTED_RESOURCES)}"
            )
        params: dict[str, Any] = {"format": "json"}
        if titel:
            params["f.titel"] = titel
        if dokumentnummer:
            params["f.dokumentnummer"] = dokumentnummer
        if zuordnung:
            params["f.zuordnung"] = zuordnung
        if wahlperiode is not None:
            params["f.wahlperiode"] = wahlperiode
        if vorgangstyp:
            params["f.vorgangstyp"] = vorgangstyp
        if date_start:
            params["f.datum.start"] = date_start
        if date_end:
            params["f.datum.end"] = date_end
        if cursor:
            params["cursor"] = cursor

        url = f"{self.base_url}/api/v1/{resource}"
        cache_key = f"dip-search::{url}::{sorted(params.items())!r}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[no-any-return]

        data = await self._get_json_with_backoff(url, params=params)
        self._cache.set(cache_key, data, ttl=_SEARCH_TTL_SECONDS)
        return data

    async def get_document(self, resource: str, doc_id: str) -> dict[str, Any]:
        """Fetch one entity by id, e.g. ``get_document("drucksache-text", "258173")``.

        Use the ``*-text`` resource variants to get the full ``text`` field.
        """
        if resource not in SUPPORTED_RESOURCES:
            raise ValueError(
                f"Unsupported DIP resource {resource!r}. Supported: {sorted(SUPPORTED_RESOURCES)}"
            )
        doc_id = doc_id.strip()
        url = f"{self.base_url}/api/v1/{resource}/{doc_id}"
        cache_key = f"dip-doc::{url}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[no-any-return]

        data = await self._get_json_with_backoff(url, params={"format": "json"})
        self._cache.set(cache_key, data, ttl=_DOCUMENT_TTL_SECONDS)
        return data
