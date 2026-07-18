"""FastMCP entry point - 5 super-tools for the NeuRIS API.

Run:

    python -m de_eli_mcp.server

Configuration via env:

- ``DE_ELI_CACHE_DIR`` (default ``~/.matematic/cache/de-eli``)
- ``DE_ELI_AUDIT_DIR`` (default ``~/.matematic/audit``)
- ``DE_ELI_BASE_URL`` (default ``https://testphase.rechtsinformationen.bund.de``)
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .audit import AuditLogger, hash_input, timer
from .citations import (
    enrich_decision_payload,
    enrich_dip_document,
    enrich_legislation_payload,
    enrich_oldp_case,
    enrich_rii_decision,
    parse_eli,
    pick_encoding_content_url,
)
from .client import DEFAULT_BASE_URL, NeurisClient, extract_search_items
from .dip_client import DEFAULT_BASE_URL as DIP_DEFAULT_BASE_URL
from .dip_client import PUBLIC_API_KEY as DIP_PUBLIC_API_KEY
from .dip_client import DipClient
from .models import (
    Act,
    ActInfo,
    ActText,
    CaseSearchQuery,
    CaseSearchResult,
    Decision,
    DecisionInfo,
    DecisionText,
    DipDocumentInfo,
    DipDocumentText,
    DipSearchQuery,
    DipSearchResult,
    OldpCaseInfo,
    OldpCaseQuery,
    OldpCaseSearchResult,
    OldpCaseText,
    Publisher,
    RiiCaseInfo,
    RiiCaseQuery,
    RiiCaseSearchResult,
    RiiCaseText,
    SearchQuery,
    SearchResult,
    TextFormat,
)
from .oldp_client import DEFAULT_BASE_URL as OLDP_DEFAULT_BASE_URL
from .oldp_client import OldpClient, normalize_case_item
from .rii_client import DEFAULT_BASE_URL as RII_DEFAULT_BASE_URL
from .rii_client import RiiClient, search_toc

# ---------------------------------------------------------------------------
# Instructions (procedural orchestration) - injected into the MCP client's
# system prompt. The LLM sees this BEFORE the first tool call.
# The drift test (tests/test_instructions_drift.py) fails if a tool in
# INSTRUCTIONS is not registered or an ErrorCode is undocumented.
# Pattern from dograh-hq/dograh v1.31.0 (BSD-2) via mcp-eu-compliance v0.2.0.
# ---------------------------------------------------------------------------

INSTRUCTIONS = """\
This MCP server exposes the German NeuRIS API (rechtsinformationen.bund.de) - official federal legislation (Gesetze, Verordnungen) published by the Bundesministerium der Justiz. Every response carries a stable `eli_uri`, a `human_readable_citation` and a `source_url` (the citation contract). NeuRIS is in beta: the dataset is incomplete, so every response also carries a `dataset_note`.

## Call order

### A concrete act
1. `de_get_act` - if you know the ELI (e.g. `eli/bund/bgbl-1/2017/s2097/2025-01-01/1/deu`). Fastest. Returns metadata.
2. `de_get_text` - full text of an act in `html` or `xml` (LegalDocML.de). Resolves the manifestation from the act's encodings.

### Searching by metadata
3. `de_search` - searches `/v1/legislation` by `search_term`, `eli`, `date_from`/`date_to`, `temporal_coverage_from`/`temporal_coverage_to`. Up to 300 results per page (`size`), `page_index` for pagination.

### Discovery
4. `de_list_publishers` - the German publication organs (BGBl I/II, Bundesanzeiger), derived from ELI `agent` codes. NeuRIS exposes no publisher-dictionary endpoint.

### Monitoring changes
5. `de_recent_changes` - acts published since `since_iso` (ISO 8601), newest-first. Useful for a law-monitoring feature.

### Case law (federal court decisions, NeuRIS beta)
6. `de_case_search` - search decisions (`GET /v1/case-law`) by `search_term` and date. Each item carries its `ecli` (e.g. `ECLI:DE:BAG:2024:200624.U.8AZR124.23.0`). **NeuRIS case-law coverage is a small beta slice** - prefer tools 9-10 below for the six federal supreme/constitutional courts.
7. `de_get_decision` - decision metadata by `document_number` (e.g. `KARE600069049`).
8. `de_get_decision_text` - full text of a decision in `html` or `xml`.

### Case law (federal court decisions, rechtsprechung-im-internet.de - complete for these courts)
9. `de_rii_case_search` - search the official RII case-law aggregator for **BVerfG** (Bundesverfassungsgericht), **BGH** (Bundesgerichtshof), **BAG** (Bundesarbeitsgericht), **BFH** (Bundesfinanzhof), **BVerwG** (Bundesverwaltungsgericht), **BSG** (Bundessozialgericht) and **BPatG** (Bundespatentgericht). Filter by `court`, `aktenzeichen_contains` (docket-number substring), `date_from`/`date_to`. No free-text search over decision content (RII's TOC carries no full text) - use `de_rii_get_case_text` once you have a `doc_id` candidate.
10. `de_rii_get_case_text` - full text of one decision by `doc_id` (from a `de_rii_case_search` result, e.g. `JURE100055033`). Returns `titelzeile`, `leitsatz`, `tenor` and the full `content` (Tatbestand + Entscheidungsgruende/Gruende), plus the real `ecli` when the court publishes one.

For BVerfG, BGH, BAG, BFH, BVerwG or BSG, ALWAYS prefer `de_rii_case_search`/`de_rii_get_case_text` over `de_case_search` - RII is the complete, non-beta source for these six courts.

### Case law (STATE courts + full-text search, Open Legal Data)
11. `de_oldp_case_search` - search Open Legal Data (de.openlegaldata.io), a community open-data aggregator of ~424k German decisions from ~1 100 courts of ALL levels - this is the only tool here that covers STATE courts (Oberlandesgerichte, Landgerichte, Amtsgerichte, state administrative/social/labor/finance courts) and the only one with FULL-TEXT search (`text` parameter). Metadata filters: `court_slug` (e.g. 'ovgnrw'), `file_number` (exact docket number), `date_after`/`date_before`. When `text` is set the metadata filters are ignored (different upstream endpoint).
12. `de_oldp_get_case` - full decision text (HTML) by numeric `case_ref` id or slug from a `de_oldp_case_search` result.

Routing rule for case law: federal supreme/constitutional courts -> RII tools (official, complete); state courts or any full-text hunt -> OLDP tools (community, broad, not official); NeuRIS `de_case_search` last (beta slice). OLDP is ODbL-licensed open data, not an official government service - say so when completeness matters.

### Parliamentary documents / legislative history (Bundestag DIP)
13. `de_dip_search` - search DIP (dip.bundestag.de), the parliament's official documentation system: `resource` = 'drucksache' (bills, motions, reports; ~287k), 'plenarprotokoll' (plenary transcripts), 'vorgang' (legislative procedures; ~335k), or the '-text' variants to include full text. Filters: `titel`, `dokumentnummer` (e.g. '20/1'), `zuordnung` ('BT'/'BR'), `wahlperiode`, `vorgangstyp`, `date_start`/`date_end`. Pagination via opaque `cursor` (repeat the query with the returned cursor; the end is reached when it stops changing).
14. `de_dip_get_document` - one DIP entity by `resource` + `doc_id`; use 'drucksache-text'/'plenarprotokoll-text' to get the full `text`. Gesetzesbegruendungen in Drucksachen are the standard German aid of statutory interpretation - cite as e.g. "BT-Drs. 20/1" with the official PDF `source_url`.

## Hard constraints

- **ELI is the key to citability** - the German ELI is a path like `eli/{jurisdiction}/{agent}/{year}/{naturalIdentifier}/{pointInTime}/{version}/{language}`. It is returned ready in `legislationIdentifier`; do not invent it.
- **Every response has `human_readable_citation` + `source_url`** - cite both to the user (e.g. "BDSG (BGBl I, 2017 2097)").
- **No modification of official text** - the act is returned verbatim from NeuRIS.
- **Beta dataset** - relay the `dataset_note`; if an act is missing, say so rather than guessing.
- **Audit log JSONL** - every tool call appends to `~/.matematic/audit/de-eli-mcp.jsonl` (metadata + input hash only).
- **Stateless** - every call hits the upstream API; cache TTL lives client-side.

## Error iteration

Tools return a structured error with a `[code]` prefix:
- `invalid_eli` - the ELI is malformed. Expected e.g. `eli/bund/bgbl-1/2017/s2097/2025-01-01/1/deu`.
- `invalid_arg` - a parameter is out of range (e.g. `size` outside 1..300, bad date).
- `not_found` - the act or the requested manifestation does not exist. Try `de_search` to locate a concrete expression-level ELI.
- `unsupported_format` - `format` for `de_get_text` must be `html` or `xml`.
- `upstream_error` - a NeuRIS API error (HTTP, timeout, malformed). Retry once before surfacing to the user.

## Response style

- Cite acts in `human_readable_citation` form with the ELI: "BDSG (BGBl I, 2017 2097), eli/bund/bgbl-1/2017/s2097".
- NEVER invent an ELI or a date - take each from `eli_uri` / `source_url`.
- Always relay the beta `dataset_note` when coverage matters to the answer.
"""


class ELIError(Exception):
    """Structured error for de-eli MCP tools - visible to the LLM with a [code] prefix."""

    VALID_CODES = frozenset({
        "invalid_eli",
        "invalid_arg",
        "not_found",
        "unsupported_format",
        "upstream_error",
    })

    def __init__(self, code: str, message: str):
        if code not in self.VALID_CODES:
            raise ValueError(f"Unknown ELIError code: {code}. Valid: {sorted(self.VALID_CODES)}")
        self.code = code
        super().__init__(f"[{code}] {message}")


READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    idempotentHint=True,
    destructiveHint=False,
    openWorldHint=True,  # upstream NeuRIS API live
)

# Derived publisher dictionary - NeuRIS has no publisher endpoint (Q2). ELI `agent`
# codes are the publication organs. Non-exhaustive, best-effort.
_PUBLISHERS: list[dict[str, str]] = [
    {"code": "bgbl-1", "name": "Bundesgesetzblatt Teil I"},
    {"code": "bgbl-2", "name": "Bundesgesetzblatt Teil II"},
    {"code": "banz-at", "name": "Bundesanzeiger (amtlicher Teil)"},
]
_PUBLISHER_NOTE = "Derived from ELI 'agent' codes; NeuRIS exposes no publisher dictionary endpoint. Non-exhaustive."

mcp: FastMCP = FastMCP(name="de-eli-mcp", instructions=INSTRUCTIONS)


def _base_url() -> str:
    return os.environ.get("DE_ELI_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _audit() -> AuditLogger:
    return AuditLogger()


def _map_http_error(exc: Exception) -> Exception:
    """Translate an httpx 404 into a structured not_found; otherwise upstream_error."""
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
        return ELIError("not_found", "Act not found in NeuRIS. Try de_search to locate it.")
    if isinstance(exc, (httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException)):
        return ELIError("upstream_error", f"NeuRIS API error: {type(exc).__name__}: {exc}")
    return exc


# ---------------------------------------------------------------------------
# de_search
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def de_search(query: SearchQuery) -> SearchResult:
    """Search German federal legislation in NeuRIS.

    Maps to ``GET /v1/legislation``. Each item gets ``eli_uri``,
    ``human_readable_citation``, ``source_url`` (per Art. 4 CONSTITUTION).

    Args:
        query: ``SearchQuery`` - search_term, eli, date_from/to,
            temporal_coverage_from/to, size (1..300), page_index, sort.

    Returns:
        ``SearchResult`` with ``total_items`` and ``items: list[ActInfo]``.
    """
    audit = _audit()
    input_hash = hash_input(query.model_dump(mode="json"))
    base = _base_url()

    params: dict[str, Any] = {
        "searchTerm": query.search_term,
        "eli": query.eli,
        "dateFrom": query.date_from,
        "dateTo": query.date_to,
        "temporalCoverageFrom": query.temporal_coverage_from,
        "temporalCoverageTo": query.temporal_coverage_to,
        "size": query.size,
        "pageIndex": query.page_index,
        "sort": query.sort,
    }

    with timer() as t:
        try:
            async with NeurisClient(base_url=base) as client:
                raw = await client.search(params)
        except Exception as exc:
            audit.log(
                tool="de_search",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise _map_http_error(exc) from exc

    total, items_raw = extract_search_items(raw)
    items = [
        ActInfo.model_validate(enrich_legislation_payload(item, base_url=base))
        for item in items_raw
    ]
    result = SearchResult(total_items=total, items=items, query_echo=query)

    audit.log(
        tool="de_search",
        input_hash=input_hash,
        output_count_or_size=len(items),
        duration_ms=t.duration_ms,
        status="ok",
    )
    return result


# ---------------------------------------------------------------------------
# de_get_act
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def de_get_act(eli: str) -> Act:
    """Fetch act metadata from NeuRIS by ELI.

    Args:
        eli: a German ELI, e.g. ``"eli/bund/bgbl-1/2017/s2097/2025-01-01/1/deu"``
            (an API path or work-level ELI is also accepted).

    Returns:
        ``Act`` with ``eli_uri``, ``human_readable_citation``, ``source_url``.
    """
    audit = _audit()
    input_hash = hash_input({"eli": eli})
    base = _base_url()

    try:
        ref = parse_eli(eli)
    except ValueError as exc:
        raise ELIError("invalid_eli", str(exc)) from exc

    with timer() as t:
        try:
            async with NeurisClient(base_url=base) as client:
                raw = await client.get_act(ref.eli)
        except Exception as exc:
            audit.log(
                tool="de_get_act",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise _map_http_error(exc) from exc

    enriched = enrich_legislation_payload(raw, base_url=base)
    act = Act.model_validate(enriched)

    audit.log(
        tool="de_get_act",
        input_hash=input_hash,
        output_count_or_size=1,
        duration_ms=t.duration_ms,
        status="ok",
    )
    return act


# ---------------------------------------------------------------------------
# de_get_text
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def de_get_text(eli: str, format: TextFormat = "html") -> ActText:
    """Fetch the full text of an act.

    Resolves the manifestation from the act's ``encoding`` array (the contentUrl
    for the requested format) and downloads it. Format is selected by file
    extension upstream, not by Accept header.

    Args:
        eli: ELI of the act (expression level recommended).
        format: ``"html"`` or ``"xml"`` (LegalDocML.de).

    Returns:
        ``ActText`` with ``eli_uri``, ``human_readable_citation``, ``source_url``,
        ``content`` and ``content_type``.
    """
    audit = _audit()
    input_hash = hash_input({"eli": eli, "format": format})
    base = _base_url()

    if format not in ("html", "xml"):
        raise ELIError("unsupported_format", f"Unsupported format: {format!r}. Allowed: html, xml.")

    try:
        ref = parse_eli(eli)
    except ValueError as exc:
        raise ELIError("invalid_eli", str(exc)) from exc

    with timer() as t:
        try:
            async with NeurisClient(base_url=base) as client:
                act = await client.get_act(ref.eli)
                content_url = pick_encoding_content_url(act, format)
                if content_url is None:
                    raise ELIError(
                        "not_found",
                        f"No {format} manifestation for {ref.eli}. "
                        f"Use de_search to obtain a concrete expression-level ELI.",
                    )
                text, ct, fetched_url = await client.get_content(content_url)
        except ELIError:
            audit.log(
                tool="de_get_text",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
            )
            raise
        except Exception as exc:
            audit.log(
                tool="de_get_text",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise _map_http_error(exc) from exc

    enriched = enrich_legislation_payload(act, base_url=base)
    result = ActText(
        eli_uri=enriched.get("eli_uri", ref.eli),
        human_readable_citation=enriched.get("human_readable_citation"),
        source_url=fetched_url,
        format=format,
        content=text,
        content_type=ct,
        byte_size=len(text.encode("utf-8")),
    )

    audit.log(
        tool="de_get_text",
        input_hash=input_hash,
        output_count_or_size=result.byte_size or 0,
        duration_ms=t.duration_ms,
        status="ok",
    )
    return result


# ---------------------------------------------------------------------------
# de_list_publishers
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def de_list_publishers() -> list[Publisher]:
    """List the German publication organs (ELI ``agent`` codes).

    NeuRIS has no publisher-dictionary endpoint, so this is derived from the ELI
    ``agent`` slot (BGBl I/II, Bundesanzeiger). Non-exhaustive.

    Returns:
        List of ``Publisher`` (code, name, note).
    """
    audit = _audit()
    input_hash = hash_input({})

    with timer() as t:
        publishers = [
            Publisher(code=p["code"], name=p["name"], note=_PUBLISHER_NOTE) for p in _PUBLISHERS
        ]

    audit.log(
        tool="de_list_publishers",
        input_hash=input_hash,
        output_count_or_size=len(publishers),
        duration_ms=t.duration_ms,
        status="ok",
    )
    return publishers


# ---------------------------------------------------------------------------
# de_recent_changes
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def de_recent_changes(since_iso: str, limit: int = 50) -> list[ActInfo]:
    """Acts published since ``since_iso`` (ISO 8601), newest-first.

    Maps to ``GET /v1/legislation?sort=date&dateFrom=...``. Useful for a
    law-monitoring feature.

    Args:
        since_iso: a date in ISO 8601 (e.g. ``"2026-01-01"``).
        limit: max items to return (1..300).

    Returns:
        List of ``ActInfo`` enriched with the citation contract.
    """
    audit = _audit()
    input_hash = hash_input({"since": since_iso, "limit": limit})
    base = _base_url()

    if not 1 <= limit <= 300:
        raise ELIError("invalid_arg", f"limit={limit} out of range 1..300.")

    params: dict[str, Any] = {
        "dateFrom": since_iso,
        "sort": "date",
        "size": limit,
        "pageIndex": 0,
    }

    with timer() as t:
        try:
            async with NeurisClient(base_url=base) as client:
                raw = await client.search(params)
        except Exception as exc:
            audit.log(
                tool="de_recent_changes",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise _map_http_error(exc) from exc

    _total, items_raw = extract_search_items(raw)
    items = [
        ActInfo.model_validate(enrich_legislation_payload(item, base_url=base))
        for item in items_raw
    ]

    audit.log(
        tool="de_recent_changes",
        input_hash=input_hash,
        output_count_or_size=len(items),
        duration_ms=t.duration_ms,
        status="ok",
    )
    return items


# ---------------------------------------------------------------------------
# de_case_search
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def de_case_search(query: CaseSearchQuery) -> CaseSearchResult:
    """Search German federal court decisions in NeuRIS.

    Maps to ``GET /v1/case-law``. Each item gets ``ecli``,
    ``human_readable_citation``, ``source_url``.

    Args:
        query: ``CaseSearchQuery`` - search_term, date_from/to, size, page_index, sort.

    Returns:
        ``CaseSearchResult`` with ``total_items`` and ``items: list[DecisionInfo]``.
    """
    audit = _audit()
    input_hash = hash_input(query.model_dump(mode="json"))
    base = _base_url()

    params: dict[str, Any] = {
        "searchTerm": query.search_term,
        "dateFrom": query.date_from,
        "dateTo": query.date_to,
        "size": query.size,
        "pageIndex": query.page_index,
        "sort": query.sort,
    }

    with timer() as t:
        try:
            async with NeurisClient(base_url=base) as client:
                raw = await client.case_search(params)
        except Exception as exc:
            audit.log(
                tool="de_case_search",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise _map_http_error(exc) from exc

    total, items_raw = extract_search_items(raw)
    items = [
        DecisionInfo.model_validate(enrich_decision_payload(item, base_url=base))
        for item in items_raw
    ]
    result = CaseSearchResult(total_items=total, items=items, query_echo=query)

    audit.log(
        tool="de_case_search",
        input_hash=input_hash,
        output_count_or_size=len(items),
        duration_ms=t.duration_ms,
        status="ok",
    )
    return result


# ---------------------------------------------------------------------------
# de_get_decision
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def de_get_decision(document_number: str) -> Decision:
    """Fetch court-decision metadata from NeuRIS by document number.

    Args:
        document_number: NeuRIS document number, e.g. ``"KARE600069049"``.

    Returns:
        ``Decision`` with ``ecli``, ``human_readable_citation``, ``source_url``.
    """
    audit = _audit()
    input_hash = hash_input({"document_number": document_number})
    base = _base_url()

    if not document_number or not document_number.strip():
        raise ELIError("invalid_arg", "document_number must not be empty.")

    with timer() as t:
        try:
            async with NeurisClient(base_url=base) as client:
                raw = await client.get_decision(document_number)
        except Exception as exc:
            audit.log(
                tool="de_get_decision",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise _map_http_error(exc) from exc

    decision = Decision.model_validate(enrich_decision_payload(raw, base_url=base))

    audit.log(
        tool="de_get_decision",
        input_hash=input_hash,
        output_count_or_size=1,
        duration_ms=t.duration_ms,
        status="ok",
    )
    return decision


# ---------------------------------------------------------------------------
# de_get_decision_text
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def de_get_decision_text(document_number: str, format: TextFormat = "html") -> DecisionText:
    """Fetch the full text of a court decision.

    Resolves the manifestation from the decision's ``encoding`` array and downloads it.

    Args:
        document_number: NeuRIS document number, e.g. ``"KARE600069049"``.
        format: ``"html"`` or ``"xml"``.

    Returns:
        ``DecisionText`` with ``ecli``, ``human_readable_citation``, ``source_url``, ``content``.
    """
    audit = _audit()
    input_hash = hash_input({"document_number": document_number, "format": format})
    base = _base_url()

    if format not in ("html", "xml"):
        raise ELIError("unsupported_format", f"Unsupported format: {format!r}. Allowed: html, xml.")
    if not document_number or not document_number.strip():
        raise ELIError("invalid_arg", "document_number must not be empty.")

    with timer() as t:
        try:
            async with NeurisClient(base_url=base) as client:
                decision = await client.get_decision(document_number)
                content_url = pick_encoding_content_url(decision, format)
                if content_url is None:
                    raise ELIError(
                        "not_found",
                        f"No {format} manifestation for decision {document_number}.",
                    )
                text, ct, fetched_url = await client.get_content(content_url)
        except ELIError:
            audit.log(
                tool="de_get_decision_text",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
            )
            raise
        except Exception as exc:
            audit.log(
                tool="de_get_decision_text",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise _map_http_error(exc) from exc

    enriched = enrich_decision_payload(decision, base_url=base)
    result = DecisionText(
        ecli=enriched.get("ecli"),
        human_readable_citation=enriched.get("human_readable_citation"),
        source_url=fetched_url,
        format=format,
        content=text,
        content_type=ct,
        byte_size=len(text.encode("utf-8")),
    )

    audit.log(
        tool="de_get_decision_text",
        input_hash=input_hash,
        output_count_or_size=result.byte_size or 0,
        duration_ms=t.duration_ms,
        status="ok",
    )
    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# de_rii_case_search
# ---------------------------------------------------------------------------


def _rii_base_url() -> str:
    return os.environ.get("DE_RII_BASE_URL", RII_DEFAULT_BASE_URL).rstrip("/")


@mcp.tool(annotations=READ_ONLY)
async def de_rii_case_search(query: RiiCaseQuery) -> RiiCaseSearchResult:
    """Search German federal court decisions via rechtsprechung-im-internet.de (RII).

    RII is the official BMJ/juris case-law aggregator and, per the independent Legal
    Data Hunter audit, is *complete* for BVerfG, BGH, BAG, BFH, BVerwG, BSG (+ BPatG) -
    unlike NeuRIS's `/v1/case-law`, which is a small beta slice. Filters over the master
    table of contents (court, Aktenzeichen substring, date range); there is no full-text
    search (the TOC carries no decision text).

    Args:
        query: ``RiiCaseQuery`` - court, aktenzeichen_contains, date_from/to, limit, offset.

    Returns:
        ``RiiCaseSearchResult`` with ``total_items`` and ``items: list[RiiCaseInfo]``,
        each carrying a ``doc_id`` usable with ``de_rii_get_case_text``.
    """
    audit = _audit()
    input_hash = hash_input(query.model_dump(mode="json"))

    with timer() as t:
        try:
            async with RiiClient(base_url=_rii_base_url()) as client:
                toc = await client.get_toc()
        except Exception as exc:
            audit.log(
                tool="de_rii_case_search",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise ELIError("upstream_error", f"RII TOC fetch failed: {type(exc).__name__}: {exc}") from exc

        total, page = search_toc(
            toc,
            court=query.court,
            aktenzeichen_contains=query.aktenzeichen_contains,
            date_from=query.date_from,
            date_to=query.date_to,
            limit=query.limit,
            offset=query.offset,
        )

    items = [
        RiiCaseInfo(
            court_raw=it.court_raw,
            court_type=it.court_type,
            decision_date=it.decision_date,
            aktenzeichen=it.aktenzeichen,
            doc_id=it.doc_id,
            zip_url=it.zip_url,
            modified=it.modified,
            human_readable_citation=(
                f"{it.court_raw}, vom {it.decision_date} - {it.aktenzeichen}"
                if it.decision_date and it.aktenzeichen
                else it.aktenzeichen
            ),
            source_url=it.zip_url,
        )
        for it in page
    ]
    result = RiiCaseSearchResult(total_items=total, items=items, query_echo=query)

    audit.log(
        tool="de_rii_case_search",
        input_hash=input_hash,
        output_count_or_size=len(items),
        duration_ms=t.duration_ms,
        status="ok",
    )
    return result


# ---------------------------------------------------------------------------
# de_rii_get_case_text
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def de_rii_get_case_text(doc_id: str) -> RiiCaseText:
    """Fetch the full text of a decision from rechtsprechung-im-internet.de (RII).

    Args:
        doc_id: the RII document id from a ``de_rii_case_search`` result's ``doc_id``
            (e.g. ``"JURE100055033"``), or a full ZIP URL.

    Returns:
        ``RiiCaseText`` with ``ecli`` (when the court publishes one), a German
        ``human_readable_citation``, ``source_url``, and the full ``content``
        (Tatbestand + Entscheidungsgruende/Gruende).
    """
    audit = _audit()
    input_hash = hash_input({"doc_id": doc_id})

    if not doc_id or not doc_id.strip():
        raise ELIError("invalid_arg", "doc_id must not be empty.")
    doc_id = doc_id.strip()

    with timer() as t:
        try:
            async with RiiClient(base_url=_rii_base_url()) as client:
                if doc_id.startswith("http://") or doc_id.startswith("https://"):
                    zip_url = doc_id
                else:
                    toc = await client.get_toc()
                    match = next((it for it in toc if it.doc_id == doc_id), None)
                    if match is None:
                        raise ELIError(
                            "not_found",
                            f"doc_id {doc_id!r} not found in the RII table of contents. "
                            f"Use de_rii_case_search to locate a valid doc_id.",
                        )
                    zip_url = match.zip_url
                parsed = await client.get_decision_xml(zip_url)
        except ELIError:
            audit.log(
                tool="de_rii_get_case_text",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
            )
            raise
        except Exception as exc:
            audit.log(
                tool="de_rii_get_case_text",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise ELIError(
                "upstream_error", f"RII decision fetch failed: {type(exc).__name__}: {exc}"
            ) from exc

    enriched = enrich_rii_decision(parsed)
    content = enriched.get("full_text")
    result = RiiCaseText(
        doc_id=enriched.get("doknr") or doc_id,
        ecli=(
            enriched["ecli"]
            if isinstance(enriched.get("ecli"), str) and enriched["ecli"].startswith("ECLI:")
            else None
        ),
        eli_uri=enriched["eli_uri"],
        court=enriched.get("gertyp"),
        spruchkoerper=enriched.get("spruchkoerper"),
        decision_date=enriched.get("entsch_datum"),
        aktenzeichen=enriched.get("aktenzeichen"),
        doktyp=enriched.get("doktyp"),
        norm=enriched.get("norm"),
        human_readable_citation=enriched.get("human_readable_citation"),
        source_url=enriched["source_url"],
        titelzeile=enriched.get("titelzeile"),
        leitsatz=enriched.get("leitsatz"),
        tenor=enriched.get("tenor"),
        content=content,
        byte_size=len(content.encode("utf-8")) if content else None,
    )

    audit.log(
        tool="de_rii_get_case_text",
        input_hash=input_hash,
        output_count_or_size=result.byte_size or 0,
        duration_ms=t.duration_ms,
        status="ok",
    )
    return result


# ---------------------------------------------------------------------------
# de_oldp_case_search (feature 004)
# ---------------------------------------------------------------------------


def _oldp_base_url() -> str:
    return os.environ.get("DE_OLDP_BASE_URL", OLDP_DEFAULT_BASE_URL).rstrip("/")


@mcp.tool(annotations=READ_ONLY)
async def de_oldp_case_search(query: OldpCaseQuery) -> OldpCaseSearchResult:
    """Search German case law across ALL court levels via Open Legal Data.

    Open Legal Data (de.openlegaldata.io) is a community open-data aggregator
    (~424k decisions from ~1 100 courts at check). It is the only source here that
    covers STATE courts and the only one with full-text search. Database ODbL v1.0;
    the decisions themselves are gemeinfrei (§ 5 UrhG). Not an official service -
    prefer the RII tools for the six federal supreme/constitutional courts.

    Args:
        query: ``OldpCaseQuery`` - text (full-text; ignores the other filters),
            court_slug, file_number (exact), date_after/date_before, page.

    Returns:
        ``OldpCaseSearchResult`` with ``total_items`` and ``items: list[OldpCaseInfo]``,
        each carrying an ``id``/``slug`` usable with ``de_oldp_get_case``.
    """
    audit = _audit()
    input_hash = hash_input(query.model_dump(mode="json"))
    base = _oldp_base_url()

    with timer() as t:
        try:
            async with OldpClient(base_url=base) as client:
                raw = await client.search_cases(
                    text=query.text,
                    court_slug=query.court_slug,
                    file_number=query.file_number,
                    date_after=query.date_after,
                    date_before=query.date_before,
                    page=query.page,
                )
        except Exception as exc:
            audit.log(
                tool="de_oldp_case_search",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise ELIError(
                "upstream_error", f"Open Legal Data search failed: {type(exc).__name__}: {exc}"
            ) from exc

    items = [
        OldpCaseInfo.model_validate(enrich_oldp_case(normalize_case_item(it), base_url=base))
        for it in raw.get("results") or []
    ]
    result = OldpCaseSearchResult(
        total_items=int(raw.get("count") or 0), items=items, query_echo=query
    )

    audit.log(
        tool="de_oldp_case_search",
        input_hash=input_hash,
        output_count_or_size=len(items),
        duration_ms=t.duration_ms,
        status="ok",
    )
    return result


# ---------------------------------------------------------------------------
# de_oldp_get_case
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def de_oldp_get_case(case_ref: str) -> OldpCaseText:
    """Fetch the full text of one decision from Open Legal Data.

    Args:
        case_ref: a numeric OLDP case id (e.g. ``"521203"``) or a slug
            (e.g. ``"lg-nurnberg-furth-2026-05-21-8-o-486025"``) from a
            ``de_oldp_case_search`` result.

    Returns:
        ``OldpCaseText`` with ``eli_uri`` (the ECLI when the source carries one),
        a German ``human_readable_citation``, ``source_url`` (the public case page)
        and the full ``content`` (decision HTML).
    """
    audit = _audit()
    input_hash = hash_input({"case_ref": case_ref})
    base = _oldp_base_url()

    if not case_ref or not case_ref.strip():
        raise ELIError("invalid_arg", "case_ref must not be empty.")

    with timer() as t:
        try:
            async with OldpClient(base_url=base) as client:
                raw = await client.get_case(case_ref)
        except LookupError as exc:
            audit.log(
                tool="de_oldp_get_case",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
            )
            raise ELIError(
                "not_found",
                f"Case {case_ref!r} not found in Open Legal Data. "
                f"Use de_oldp_case_search to locate a valid id or slug.",
            ) from exc
        except httpx.HTTPStatusError as exc:
            audit.log(
                tool="de_oldp_get_case",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            if exc.response.status_code == 404:
                raise ELIError(
                    "not_found",
                    f"Case {case_ref!r} not found in Open Legal Data. "
                    f"Use de_oldp_case_search to locate a valid id or slug.",
                ) from exc
            raise ELIError(
                "upstream_error", f"Open Legal Data error: {type(exc).__name__}: {exc}"
            ) from exc
        except Exception as exc:
            audit.log(
                tool="de_oldp_get_case",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise ELIError(
                "upstream_error", f"Open Legal Data error: {type(exc).__name__}: {exc}"
            ) from exc

    enriched = enrich_oldp_case(normalize_case_item(raw), base_url=base)
    content = raw.get("content")
    result = OldpCaseText(
        id=enriched.get("id"),
        slug=enriched.get("slug"),
        eli_uri=enriched["eli_uri"],
        ecli=enriched.get("ecli"),
        court_name=enriched.get("court_name"),
        file_number=enriched.get("file_number"),
        date=enriched.get("date"),
        decision_type=enriched.get("decision_type"),
        human_readable_citation=enriched.get("human_readable_citation"),
        source_url=enriched["source_url"],
        content=content if isinstance(content, str) else None,
        byte_size=len(content.encode("utf-8")) if isinstance(content, str) else None,
    )

    audit.log(
        tool="de_oldp_get_case",
        input_hash=input_hash,
        output_count_or_size=result.byte_size or 0,
        duration_ms=t.duration_ms,
        status="ok",
    )
    return result


# ---------------------------------------------------------------------------
# de_dip_search (feature 004)
# ---------------------------------------------------------------------------


def _dip_base_url() -> str:
    return os.environ.get("DE_DIP_BASE_URL", DIP_DEFAULT_BASE_URL).rstrip("/")


def _dip_api_key() -> str:
    return os.environ.get("DE_DIP_API_KEY", DIP_PUBLIC_API_KEY)


@mcp.tool(annotations=READ_ONLY)
async def de_dip_search(query: DipSearchQuery) -> DipSearchResult:
    """Search the Bundestag DIP - Germany's official parliamentary documentation.

    Covers Drucksachen (bills, motions, reports, government answers), plenary
    transcripts and legislative procedures of Bundestag and Bundesrat. Legislative
    history (Gesetzesbegruendungen) is a standard aid of German statutory
    interpretation. Uses the documented public API key by default (rotates ~yearly;
    override with ``DE_DIP_API_KEY``).

    Args:
        query: ``DipSearchQuery`` - resource (drucksache / plenarprotokoll / vorgang /
            '-text' variants), titel, dokumentnummer, zuordnung ('BT'/'BR'),
            wahlperiode, vorgangstyp, date_start/date_end, cursor.

    Returns:
        ``DipSearchResult`` with ``total_items`` (numFound), ``items`` and the
        pagination ``cursor``.
    """
    audit = _audit()
    input_hash = hash_input(query.model_dump(mode="json"))

    with timer() as t:
        try:
            async with DipClient(base_url=_dip_base_url(), api_key=_dip_api_key()) as client:
                raw = await client.search(
                    query.resource,
                    titel=query.titel,
                    dokumentnummer=query.dokumentnummer,
                    zuordnung=query.zuordnung,
                    wahlperiode=query.wahlperiode,
                    vorgangstyp=query.vorgangstyp,
                    date_start=query.date_start,
                    date_end=query.date_end,
                    cursor=query.cursor,
                )
        except ValueError as exc:
            raise ELIError("invalid_arg", str(exc)) from exc
        except Exception as exc:
            audit.log(
                tool="de_dip_search",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise ELIError(
                "upstream_error", f"DIP API error: {type(exc).__name__}: {exc}"
            ) from exc

    items = [
        DipDocumentInfo.model_validate(enrich_dip_document(doc))
        for doc in raw.get("documents") or []
    ]
    result = DipSearchResult(
        total_items=int(raw.get("numFound") or 0),
        items=items,
        cursor=raw.get("cursor"),
        query_echo=query,
    )

    audit.log(
        tool="de_dip_search",
        input_hash=input_hash,
        output_count_or_size=len(items),
        duration_ms=t.duration_ms,
        status="ok",
    )
    return result


# ---------------------------------------------------------------------------
# de_dip_get_document
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def de_dip_get_document(resource: str, doc_id: str) -> DipDocumentText:
    """Fetch one entity from the Bundestag DIP by id.

    Args:
        resource: ``"drucksache"``, ``"drucksache-text"``, ``"plenarprotokoll"``,
            ``"plenarprotokoll-text"`` or ``"vorgang"``. Use a ``-text`` variant to
            get the full document text.
        doc_id: the DIP entity id from a ``de_dip_search`` result (e.g. ``"258173"``).

    Returns:
        ``DipDocumentText`` with a parliamentary ``human_readable_citation``
        (e.g. ``"BT-Drs. 20/1"``), the official PDF as ``source_url`` and - for
        ``-text`` resources - the full ``content``.
    """
    audit = _audit()
    input_hash = hash_input({"resource": resource, "doc_id": doc_id})

    if not doc_id or not doc_id.strip():
        raise ELIError("invalid_arg", "doc_id must not be empty.")

    with timer() as t:
        try:
            async with DipClient(base_url=_dip_base_url(), api_key=_dip_api_key()) as client:
                raw = await client.get_document(resource, doc_id)
        except ValueError as exc:
            raise ELIError("invalid_arg", str(exc)) from exc
        except httpx.HTTPStatusError as exc:
            audit.log(
                tool="de_dip_get_document",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            if exc.response.status_code == 404:
                raise ELIError(
                    "not_found",
                    f"DIP entity {doc_id!r} not found for resource {resource!r}. "
                    f"Use de_dip_search to locate a valid id.",
                ) from exc
            raise ELIError(
                "upstream_error", f"DIP API error: {type(exc).__name__}: {exc}"
            ) from exc
        except Exception as exc:
            audit.log(
                tool="de_dip_get_document",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise ELIError(
                "upstream_error", f"DIP API error: {type(exc).__name__}: {exc}"
            ) from exc

    enriched = enrich_dip_document(raw)
    content = raw.get("text")
    result = DipDocumentText(
        id=str(enriched["id"]) if enriched.get("id") is not None else None,
        eli_uri=enriched["eli_uri"],
        dokumentart=enriched.get("dokumentart"),
        dokumentnummer=enriched.get("dokumentnummer"),
        wahlperiode=enriched.get("wahlperiode"),
        herausgeber=enriched.get("herausgeber"),
        titel=enriched.get("titel"),
        datum=enriched.get("datum"),
        human_readable_citation=enriched.get("human_readable_citation"),
        source_url=enriched["source_url"],
        content=content if isinstance(content, str) else None,
        byte_size=len(content.encode("utf-8")) if isinstance(content, str) else None,
    )

    audit.log(
        tool="de_dip_get_document",
        input_hash=input_hash,
        output_count_or_size=result.byte_size or 0,
        duration_ms=t.duration_ms,
        status="ok",
    )
    return result


def _run_http() -> None:
    """Serve streamable HTTP on ``/mcp`` for container hosts (Smithery).

    CORS with the two ``mcp-*`` response headers exposed is required, otherwise
    browser-based MCP clients cannot read the session id and every call fails.
    """
    import uvicorn
    from starlette.middleware import Middleware
    from starlette.middleware.cors import CORSMiddleware

    app = mcp.http_app(
        path="/mcp",
        transport="http",
        middleware=[
            Middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
                allow_headers=["*"],
                expose_headers=["mcp-session-id", "mcp-protocol-version"],
                max_age=86400,
            )
        ],
    )
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))


def main() -> None:
    """Run the MCP server: stdio by default, HTTP when ``TRANSPORT=http``."""
    if os.environ.get("TRANSPORT", "").strip().lower() == "http":
        _run_http()
        return
    mcp.run()


if __name__ == "__main__":
    main()
