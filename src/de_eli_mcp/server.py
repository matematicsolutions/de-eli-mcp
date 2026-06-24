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
    enrich_legislation_payload,
    parse_eli,
    pick_encoding_content_url,
)
from .client import DEFAULT_BASE_URL, NeurisClient, extract_search_items
from .models import (
    Act,
    ActInfo,
    ActText,
    CaseSearchQuery,
    CaseSearchResult,
    Decision,
    DecisionInfo,
    DecisionText,
    Publisher,
    SearchQuery,
    SearchResult,
    TextFormat,
)

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

### Case law (federal court decisions)
6. `de_case_search` - search decisions (`GET /v1/case-law`) by `search_term` and date. Each item carries its `ecli` (e.g. `ECLI:DE:BAG:2024:200624.U.8AZR124.23.0`).
7. `de_get_decision` - decision metadata by `document_number` (e.g. `KARE600069049`).
8. `de_get_decision_text` - full text of a decision in `html` or `xml`.

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


def main() -> None:
    """Run the MCP server over stdio (default for Claude Code)."""
    mcp.run()


if __name__ == "__main__":
    main()
