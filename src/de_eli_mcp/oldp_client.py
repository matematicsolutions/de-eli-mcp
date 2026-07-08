"""Async client for Open Legal Data (de.openlegaldata.io) - feature 004.

Open Legal Data (OLDP, openlegaldata.io) is a community/open-data aggregator of German
case law across ALL court levels - federal courts, state courts (Oberlandesgerichte,
Landgerichte, Amtsgerichte, Verwaltungs-/Sozial-/Arbeits-/Finanzgerichte of the
Laender). Live total at check (2026-07-08): 423 944 decisions from 1 119 courts, with
full decision text (HTML) per case. This complements ``rii_client.py``: RII is the
official-but-federal-only source (~83k decisions, 7 courts); OLDP adds the state-court
layer the juris Landesrecht portals keep behind a session-bound, TDM-reserved UI.

API: keyless REST (Django REST Framework) at ``https://de.openlegaldata.io/api``.

Two search shapes, normalised here into one:

- ``GET /api/cases/`` - metadata filters. Verified live: ``court__slug`` (e.g.
  ``bverwg``), ``court__state`` (numeric id), ``file_number`` (EXACT match),
  ``date_after`` / ``date_before`` (ISO). WARNING: ``date__gte`` and friends silently
  no-op (they return the unfiltered total) - only the parameter names above actually
  narrow. Response: ``{count, next, previous, results[]}``.
- ``GET /api/cases/search/?text=...`` - full-text search (Elasticsearch-backed) with
  highlight ``snippets``; items carry ``court`` as a short code string, not an object.

Full text: ``GET /api/cases/{id}/`` returns ``content`` (decision HTML).

Licence: database ODbL v1.0; the decisions themselves are gemeinfrei (§ 5 UrhG). Both
stated on https://de.openlegaldata.io/imprint/ (checked 2026-07-08).
"""

from __future__ import annotations

from typing import Any

import anyio
import httpx

from .cache import HttpCache

DEFAULT_BASE_URL = "https://de.openlegaldata.io"
DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
USER_AGENT = "de-eli-mcp/0.3.0 (+https://github.com/matematicsolutions/de-eli-mcp)"

_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3

# Search pages are re-crawled often upstream; cache briefly to be a polite client
# without going stale. Case detail (final decisions) can live longer.
_SEARCH_TTL_SECONDS = 15 * 60
_CASE_TTL_SECONDS = 7 * 24 * 60 * 60


def normalize_case_item(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalise a case item from either endpoint shape into one flat dict.

    ``/api/cases/`` items carry ``court`` as an object; ``/api/cases/search/`` items
    carry ``court`` as a short code string plus highlight ``snippets``.
    """
    court = raw.get("court")
    if isinstance(court, dict):
        court_name = court.get("name")
        court_slug = court.get("slug")
        court_jurisdiction = court.get("jurisdiction")
        court_level = court.get("level_of_appeal")
    else:
        court_name = court if isinstance(court, str) else None
        court_slug = None
        court_jurisdiction = raw.get("court_jurisdiction")
        court_level = raw.get("court_level_of_appeal")

    snippets = raw.get("snippets")
    snippet_texts: list[str] = []
    if isinstance(snippets, list):
        for s in snippets:
            if isinstance(s, dict) and isinstance(s.get("text"), str):
                snippet_texts.append(s["text"])

    ecli = raw.get("ecli")
    return {
        "id": raw.get("id"),
        "slug": raw.get("slug"),
        "court_name": court_name,
        "court_slug": court_slug,
        "court_jurisdiction": court_jurisdiction,
        "court_level_of_appeal": court_level,
        "file_number": raw.get("file_number"),
        "date": raw.get("date"),
        "decision_type": raw.get("type") or raw.get("decision_type"),
        "ecli": ecli.strip() if isinstance(ecli, str) and ecli.strip() else None,
        "snippets": snippet_texts or None,
    }


class OldpClient:
    """Async client for de.openlegaldata.io. Use as ``async with OldpClient() as c:``."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        cache: HttpCache | None = None,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._cache = cache or HttpCache()
        self._http = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            follow_redirects=True,
        )

    async def __aenter__(self) -> OldpClient:
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

    async def search_cases(
        self,
        *,
        text: str | None = None,
        court_slug: str | None = None,
        file_number: str | None = None,
        date_after: str | None = None,
        date_before: str | None = None,
        page: int = 1,
    ) -> dict[str, Any]:
        """Search cases; full-text (``text``) routes to ``/api/cases/search/``,
        metadata filters route to ``/api/cases/``. Returns the raw DRF envelope
        ``{count, next, previous, results}`` (items NOT yet normalised).
        """
        if text:
            url = f"{self.base_url}/api/cases/search/"
            params: dict[str, Any] = {"text": text, "format": "json", "page": page}
            # The search endpoint ignores metadata filters - do not pretend otherwise.
        else:
            url = f"{self.base_url}/api/cases/"
            params = {"format": "json", "page": page}
            if court_slug:
                params["court__slug"] = court_slug
            if file_number:
                params["file_number"] = file_number
            # Only date_after/date_before narrow; date__gte silently no-ops (verified
            # live 2026-07-08: date__gte returned the full unfiltered count).
            if date_after:
                params["date_after"] = date_after
            if date_before:
                params["date_before"] = date_before

        cache_key = f"oldp-search::{url}::{sorted(params.items())!r}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[no-any-return]

        data = await self._get_json_with_backoff(url, params=params)
        self._cache.set(cache_key, data, ttl=_SEARCH_TTL_SECONDS)
        return data

    async def get_case(self, case_ref: str) -> dict[str, Any]:
        """Fetch one case with full ``content``. ``case_ref`` is a numeric id or a slug.

        A slug resolves via ``/api/cases/?slug=...`` (exact, verified live) to the id,
        then the detail endpoint is fetched.
        """
        ref = case_ref.strip()
        cache_key = f"oldp-case::{ref}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[no-any-return]

        if ref.isdigit():
            url = f"{self.base_url}/api/cases/{ref}/"
            data = await self._get_json_with_backoff(url, params={"format": "json"})
        else:
            listing = await self._get_json_with_backoff(
                f"{self.base_url}/api/cases/", params={"slug": ref, "format": "json"}
            )
            results = listing.get("results") or []
            if not results:
                raise LookupError(f"No OLDP case with slug {ref!r}")
            case_id = results[0]["id"]
            url = f"{self.base_url}/api/cases/{case_id}/"
            data = await self._get_json_with_backoff(url, params={"format": "json"})

        self._cache.set(cache_key, data, ttl=_CASE_TTL_SECONDS)
        return data
