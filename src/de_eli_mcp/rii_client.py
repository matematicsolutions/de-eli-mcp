"""Async client for rechtsprechung-im-internet.de (RII) - the official German federal
courts' case-law aggregator (BMJ / juris GmbH), covering the courts whose decisions are
declared *complete* by the independent Legal Data Hunter catalogue (worldwidelaw/legal-sources):
BVerfG, BGH, BAG, BFH, BVerwG, BSG (plus BPatG, exposed here as a bonus).

Unlike NeuRIS (``client.py``, beta, incomplete dataset, query API), RII has no search
API. It publishes a single master table-of-contents XML
(``https://www.rechtsprechung-im-internet.de/rii-toc.xml``, ~80k decisions, ~23 MB) with
one ``<item>`` per decision (``gericht``, ``entsch-datum``, ``aktenzeichen``, a ``link``
to a per-decision ZIP, ``modified``). Full text (including a real ``ecli`` when the court
publishes one) lives in the single XML file inside that ZIP.

Strategy: download + cache the TOC once (long TTL - it is regenerated nightly upstream
per its own DOCTYPE comment), filter/search it in memory (court, date range, Aktenzeichen
substring, free-text over Aktenzeichen - the TOC carries no full text), then fetch+unzip
the single matching decision on demand for full text.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree as ET

import anyio
import httpx

from .cache import HttpCache

DEFAULT_BASE_URL = "https://www.rechtsprechung-im-internet.de"
DEFAULT_TOC_PATH = "/rii-toc.xml"
DEFAULT_TIMEOUT = httpx.Timeout(120.0, connect=10.0)
USER_AGENT = "de-eli-mcp/0.3.0 (+https://github.com/matematicsolutions/de-eli-mcp)"

_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3

# The six "complete" federal supreme/constitutional courts per the Legal Data Hunter
# audit, plus BPatG (also served by the same RII infrastructure, bonus coverage).
SUPPORTED_COURTS = frozenset({"BVerfG", "BGH", "BAG", "BFH", "BVerwG", "BSG", "BPatG"})

# TOC entries are refreshed nightly upstream; a long client-side TTL avoids re-pulling
# the ~23 MB file on every call while staying within a day of upstream reality.
_TOC_TTL_SECONDS = 12 * 60 * 60


@dataclass(frozen=True)
class RiiTocItem:
    """One row of the RII master table of contents."""

    court_raw: str  # e.g. "BGH 9. Zivilsenat" (gertyp + Spruchkoerper, as published)
    court_type: str  # e.g. "BGH" (first whitespace-separated token)
    decision_date: str | None  # "YYYYMMDD" as published, may be empty
    aktenzeichen: str | None
    zip_url: str
    modified: str | None

    @property
    def doc_id(self) -> str:
        """Stable id derived from the ZIP filename (also the RII ``doknr``), e.g.
        ``JURE100055033``. This is what ``de_rii_get_case_text`` accepts."""
        name = self.zip_url.rsplit("/", 1)[-1]
        stem = name[:-4] if name.lower().endswith(".zip") else name
        return stem[3:] if stem.startswith("jb-") else stem


def _court_type(gericht: str | None) -> str:
    if not gericht:
        return ""
    return gericht.split()[0] if gericht.split() else ""


def parse_toc(xml_bytes: bytes) -> list[RiiTocItem]:
    """Parse the RII master TOC XML into a list of items.

    Tolerant of the DOCTYPE-internal-subset declaration (stdlib ``ElementTree`` skips
    it); does not validate against the DTD.
    """
    root = ET.fromstring(xml_bytes)
    items: list[RiiTocItem] = []
    for el in root.findall("item"):
        gericht = (el.findtext("gericht") or "").strip()
        link = (el.findtext("link") or "").strip()
        if not link:
            continue
        items.append(
            RiiTocItem(
                court_raw=gericht,
                court_type=_court_type(gericht),
                decision_date=(el.findtext("entsch-datum") or "").strip() or None,
                aktenzeichen=(el.findtext("aktenzeichen") or "").strip() or None,
                zip_url=link,
                modified=(el.findtext("modified") or "").strip() or None,
            )
        )
    return items


def parse_decision_xml(xml_bytes: bytes) -> dict[str, Any]:
    """Parse a single RII decision XML (``<dokument>``) into a flat dict.

    Field names mirror the RII DTD (``rii-dok.dtd``) verbatim where practical:
    doknr, ecli, gertyp, spruchkoerper, entsch_datum, aktenzeichen, doktyp, norm,
    titelzeile, leitsatz, tenor, tatbestand, entscheidungsgruende, gruende,
    identifier, region, publisher.

    ``full_text`` concatenates the human-readable sections in reading order
    (titelzeile, leitsatz, tenor, tatbestand, entscheidungsgruende, gruende) - this is
    what ``de_rii_get_case_text`` returns as ``content``.
    """
    root = ET.fromstring(xml_bytes)

    def _text(tag: str) -> str | None:
        el = root.find(tag)
        if el is None:
            return None
        val = "".join(el.itertext()).strip()
        return val or None

    def _section(tag: str) -> str | None:
        el = root.find(tag)
        if el is None:
            return None
        val = re.sub(r"[ \t]+", " ", "\n".join(
            line.strip() for line in "".join(el.itertext()).splitlines()
        )).strip()
        return val or None

    sections = {
        "titelzeile": _section("titelzeile"),
        "leitsatz": _section("leitsatz"),
        "tenor": _section("tenor"),
        "tatbestand": _section("tatbestand"),
        "entscheidungsgruende": _section("entscheidungsgruende"),
        "gruende": _section("gruende"),
    }
    full_text = "\n\n".join(v for v in sections.values() if v)

    region_el = root.find("region/long")
    publisher = _text("publisher")
    identifier = _text("identifier")

    return {
        "doknr": _text("doknr"),
        "ecli": _text("ecli"),
        "gertyp": _text("gertyp"),
        "spruchkoerper": _text("spruchkoerper"),
        "entsch_datum": _text("entsch-datum"),
        "aktenzeichen": _text("aktenzeichen"),
        "doktyp": _text("doktyp"),
        "norm": _text("norm"),
        "vorinstanz": _text("vorinstanz"),
        "region": region_el.text if region_el is not None else None,
        **sections,
        "full_text": full_text or None,
        "identifier": identifier,
        "publisher": publisher,
    }


class RiiClient:
    """Async client for rechtsprechung-im-internet.de. Use as
    ``async with RiiClient() as c: ...``."""

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
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )

    async def __aenter__(self) -> RiiClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()
        self._cache.close()

    async def _get_bytes_with_backoff(self, url: str) -> bytes:
        last_exc: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                resp = await self._http.get(url)
                resp.raise_for_status()
                return resp.content
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

    async def get_toc(self) -> list[RiiTocItem]:
        """Fetch (or serve from cache) the master TOC, parsed into ``RiiTocItem`` rows."""
        cache_key = f"rii-toc::{self.base_url}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return [RiiTocItem(**row) for row in cached]

        url = f"{self.base_url}{DEFAULT_TOC_PATH}"
        raw = await self._get_bytes_with_backoff(url)
        items = parse_toc(raw)
        serializable = [item.__dict__ for item in items]
        self._cache.set(cache_key, serializable, ttl=_TOC_TTL_SECONDS)
        return items

    async def get_decision_xml(self, zip_url: str) -> dict[str, Any]:
        """Download a decision ZIP, unzip its single XML member, and parse it."""
        cache_key = f"rii-doc::{zip_url}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        raw = await self._get_bytes_with_backoff(zip_url)
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                names = [n for n in zf.namelist() if n.lower().endswith(".xml")]
                if not names:
                    raise ValueError(f"No XML member in {zip_url}")
                xml_bytes = zf.read(names[0])
        except zipfile.BadZipFile as exc:
            raise ValueError(f"Not a valid ZIP at {zip_url}: {exc}") from exc

        parsed = parse_decision_xml(xml_bytes)
        parsed["_source_zip_url"] = zip_url
        self._cache.set(cache_key, parsed, ttl=30 * 24 * 60 * 60)  # decisions never change
        return parsed


def search_toc(
    items: list[RiiTocItem],
    *,
    court: str | None = None,
    aktenzeichen_contains: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[int, list[RiiTocItem]]:
    """Filter the in-memory TOC. Dates are ``YYYYMMDD`` or ``YYYY-MM-DD`` (normalised).

    Returns ``(total_matching, page)``. No free-text/full-text search - the TOC does not
    carry decision text; use ``de_rii_get_case_text`` for that once a candidate is found.
    """

    def _norm_date(d: str | None) -> str | None:
        if not d:
            return None
        return d.replace("-", "")[:8]

    court_u = court.strip().upper() if court else None
    akt_needle = aktenzeichen_contains.strip().lower() if aktenzeichen_contains else None
    d_from = _norm_date(date_from)
    d_to = _norm_date(date_to)

    matched: list[RiiTocItem] = []
    for it in items:
        if court_u and it.court_type.upper() != court_u:
            continue
        if akt_needle and (not it.aktenzeichen or akt_needle not in it.aktenzeichen.lower()):
            continue
        if d_from and (not it.decision_date or it.decision_date < d_from):
            continue
        if d_to and (not it.decision_date or it.decision_date > d_to):
            continue
        matched.append(it)

    # Newest first - most useful default ordering for legal research.
    matched.sort(key=lambda it: it.decision_date or "", reverse=True)
    total = len(matched)
    page = matched[offset : offset + limit]
    return total, page
