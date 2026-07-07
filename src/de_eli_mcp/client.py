"""Async httpx client for the NeuRIS API (rechtsinformationen.bund.de) with cache.

NeuRIS differs from the Polish ELI API: legislation is addressed by an 8-segment FRBR
ELI path, search returns a Hydra collection (``member[].item``), and full text is fetched
via the ``contentUrl`` exposed in each act's ``encoding`` array (format chosen by file
extension, not Accept). No API key. Rate-limit is undocumented, so we keep our own
backoff + cache.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import anyio
import httpx

from .cache import HttpCache

DEFAULT_BASE_URL = "https://testphase.rechtsinformationen.bund.de"
DEFAULT_TIMEOUT = httpx.Timeout(40.0, connect=10.0)
USER_AGENT = "de-eli-mcp/0.2.0 (+https://github.com/matematicsolutions/de-eli-mcp)"

_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3


class NeurisClient:
    """Async client. Use as ``async with NeurisClient() as c: ...``."""

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
        )

    async def __aenter__(self) -> NeurisClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()
        self._cache.close()

    # ----- low-level ---------------------------------------------------------

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.base_url}{path}"

    def _cache_key(self, url: str, params: dict[str, Any] | None) -> str:
        if not params:
            return url
        items = sorted((k, v) for k, v in params.items() if v is not None)
        return f"{url}?{urlencode(items, doseq=True)}"

    async def _request_with_backoff(
        self, url: str, params: dict[str, Any] | None, *, accept: str
    ) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                resp = await self._http.get(url, params=params, headers={"Accept": accept})
                resp.raise_for_status()
                return resp
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if exc.response.status_code not in _RETRY_STATUS or attempt == _MAX_ATTEMPTS - 1:
                    raise
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt == _MAX_ATTEMPTS - 1:
                    raise
            await anyio.sleep(0.5 * (2**attempt))  # 0.5s, 1s
        assert last_exc is not None
        raise last_exc

    async def _get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        category: str = "list",
    ) -> Any:
        url = self._url(path)
        key = self._cache_key(url, params)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        resp = await self._request_with_backoff(url, clean or None, accept="application/json")
        data = resp.json()
        self._cache.set(key, data, ttl=HttpCache.ttl_for(category))
        return data

    async def _get_text(self, path: str, *, category: str = "act") -> tuple[str, str | None]:
        url = self._url(path)
        key = "text::" + url
        cached = self._cache.get(key)
        if cached is not None and isinstance(cached, list) and len(cached) == 2:
            return cached[0], cached[1]
        # text manifestations are negotiated by extension; ask broadly.
        resp = await self._request_with_backoff(url, None, accept="*/*")
        text = resp.text
        ct = resp.headers.get("content-type")
        self._cache.set(key, [text, ct], ttl=HttpCache.ttl_for(category))
        return text, ct

    # ----- typed endpoints ---------------------------------------------------

    async def search(self, params: dict[str, Any]) -> dict[str, Any]:
        data = await self._get_json("/v1/legislation", params=params, category="search")
        if not isinstance(data, dict):
            return {"totalItems": 0, "member": []}
        return data

    async def get_act(self, eli: str) -> dict[str, Any]:
        path = f"/v1/legislation/{eli.lstrip('/')}"
        data = await self._get_json(path, category="act")
        if not isinstance(data, dict):
            raise ValueError(f"Unexpected response shape for {path}: {type(data).__name__}")
        return data

    async def get_content(self, content_url: str) -> tuple[str, str | None, str]:
        """Fetch a manifestation by its contentUrl. Returns (text, content_type, source_url)."""
        text, ct = await self._get_text(content_url, category="act")
        return text, ct, self._url(content_url)

    async def statistics(self) -> dict[str, Any]:
        data = await self._get_json("/v1/statistics", category="dict")
        return data if isinstance(data, dict) else {}

    async def case_search(self, params: dict[str, Any]) -> dict[str, Any]:
        data = await self._get_json("/v1/case-law", params=params, category="search")
        if not isinstance(data, dict):
            return {"totalItems": 0, "member": []}
        return data

    async def get_decision(self, document_number: str) -> dict[str, Any]:
        path = f"/v1/case-law/{document_number.strip().lstrip('/')}"
        data = await self._get_json(path, category="act")
        if not isinstance(data, dict):
            raise ValueError(f"Unexpected response shape for {path}: {type(data).__name__}")
        return data


def extract_search_items(raw: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    """Flatten a Hydra collection into (total_items, [legislation dicts]).

    NeuRIS shape: ``{"totalItems": N, "member": [{"item": {...Legislation...}}, ...]}``.
    """
    total = raw.get("totalItems")
    members = raw.get("member", [])
    items: list[dict[str, Any]] = []
    if isinstance(members, list):
        for m in members:
            if isinstance(m, dict):
                item = m.get("item")
                if isinstance(item, dict):
                    items.append(item)
                elif m.get("@type") == "Legislation":
                    items.append(m)
    if not isinstance(total, int):
        total = len(items)
    return total, items
