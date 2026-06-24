# Discovery: NeuRIS API (rechtsinformationen.bund.de) - Germany

Date: 2026-06-24
Author: discovery commissioned by Wieslaw Mazur. **Status: CLOSED** (confirmed from the OpenAPI). One open
point remains (data licence) - non-blocking for the build, blocking for public distribution.

Based on the official OpenAPI spec at `https://docs.rechtsinformationen.bund.de/v3/api-docs`
(Swagger UI: `/swagger-ui/index.html`). An operational distillation oriented to the 5 MCP super-tools.

## Base API properties (CONFIRMED)

- **Base URL:** `https://testphase.rechtsinformationen.bund.de` (beta phase).
- **OpenAPI:** `https://docs.rechtsinformationen.bund.de/v3/api-docs` | Swagger UI `/swagger-ui/index.html`.
- **Authentication:** none - **no API key**. (Keyless and public, so this connector qualifies for drop-in, "as simple as a skill" distribution.)
- **Rate-limit:** none documented in the OpenAPI (a `/guides/rate-limiting/` guide exists - own backoff + cache mandatory regardless).
- **Formats:** `application/json` (default), `application/xml` (LegalDocML.de), `text/html`, `application/zip` (bulk).
- **Identifiers:** **ELI** (legislation, work level) + **ECLI** (case law) + **eId** (expression/fragment level). **FRBR Work/Expression/Manifestation** model.
- **Scope:** legislation, federal court case law, literature, administrative directives. Verwaltungsvorschriften planned.
- **Operator caveat:** dataset incomplete (beta) - for full research the portal points to gesetze-im-internet.de and rechtsprechung-im-internet.de.

## Endpoints (from the OpenAPI)

| Endpoint | Method | Purpose |
|---|---|---|
| `/v1/statistics` | GET | document counts |
| `/v1/legislation` | GET | list/search acts (filters + pagination) |
| `/v1/legislation/eli/{jurisdiction}/{agent}/{year}/{naturalIdentifier}/{pointInTime}/{version}/{language}` | GET | act metadata (work/expression) by ELI |
| `.../{pointInTimeManifestation}/{subtype}.xml` or `.html` | GET | **full text** (format selected by FILE EXTENSION, not Accept) |
| `/v1/case-law` | GET | search decisions (ECLI) |
| `/v1/case-law/{documentNumber}` | GET | decision metadata |
| `/v1/literature` | GET | literature |
| `/v1/document` | GET | global cross-kind search |
| `/v1/administrative-directive` | GET | administrative directives |
| `/v1/bulk-zip-links` | GET | bulk download links |

### `/v1/legislation` parameters

`eli`, `searchTerm` (token-based, all tokens required), `temporalCoverageFrom/To`, `dateFrom/dateTo`,
`size` (max 300), `pageIndex`, `sort` (`date` / `temporalCoverageFrom` / `legislationIdentifier`).

### ELI example

`/v1/legislation/eli/bund/bgbl-1/1979/s1325/2020-06-19/2/deu`
(jurisdiction=bund, agent=bgbl-1, year=1979, naturalIdentifier=s1325, pointInTime, version, language=deu)

## Schema fields (for the citation contract)

- `legislationIdentifier` - the **full ELI string** -> `eli_uri`.
- `@id` - URI.
- `abbreviation` - Amtliche Buchstabenabkurzung (e.g. "KakaoV 2003").
- `alternateName` - Amtliche Kurzuberschrift.
- `name` - Amtliche Languberschrift (official long title).
- `encoding[]` - `LegislationObjectSchema` with a `contentUrl` field (manifestation links).

## Mapping to the 5 super-tools (CONFIRMED)

| Super-tool | Endpoint | Notes |
|---|---|---|
| `de_search` | `/v1/legislation` (+ optional `/v1/document` cross-kind) | MVP core; searchTerm + eli + date filters |
| `de_get_act` | `/v1/legislation/eli/{...}` | work/expression metadata |
| `de_get_text` | `.../{manifestation}/{subtype}.xml` or `.html` | format = file extension |
| `de_list_publishers` | no dedicated endpoint -> derive from `agent` codes (bgbl-1, bgbl-2, banz...) or `/v1/statistics` | probably a static dictionary |
| `de_recent_changes` | `/v1/legislation?sort=date&dateFrom=...` | sort descending by date; optionally `/v1/bulk-zip-links` for dumps |

**Phase 2 (case law, ECLI):** `de_case_search` -> `/v1/case-law`; `de_get_decision` -> `/v1/case-law/{documentNumber}`. Same API, separate sub-family of tools.

## Citation contract (Article IV) - CLOSED for DE

- `eli_uri` = `legislationIdentifier` (full ELI). **ELI available at the source - no compromise, Article IV met directly.**
- `human_readable_citation` = `abbreviation` or `alternateName` + a BGBl reference (e.g. "KakaoV 2003"; "BGBl. I 1979 S. 1325").
- `source_url` = a deep link to the document on rechtsinformationen.bund.de (from `@id` / `contentUrl`).

## Decision: BUILD

All 3 blocking questions from the CONSTITUTION resolved in favour: (1) ELI YES; (2) base URL + contract YES;
(3) keyless YES. Reuse from `sejm-eli-mcp` is high - skeleton copied, the `client.py` adapter is new (ELI FRBR
paths + content negotiation via file extension).

### Remaining risks / open points (non-blocking)

1. **NeuRIS data licence / re-use terms** - RESOLVED (2026-06-24): German official works are gemeinfrei under
   § 5 UrhG; NeuRIS (BMJV / DigitalService GmbH) publishes no separate API terms or key. Residual watch-item:
   re-check at general availability, as the beta may formalize usage conditions.
2. **Beta - incomplete dataset.** `de_get_*` must return an explicit completeness note; consider a
   gesetze-im-internet.de (XML) fallback as a backup source. Ties into "freshness / fail-loud = first-class feature".
3. **Undocumented rate-limit** - own backoff + cache regardless.

## Next step

`matematic-spec-driven` phases 2-4 for `de-eli-mcp`: spec (US1=de_search MVP, US2=get_act/get_text,
US3=recent_changes; case-law as a separate feature 002), plan (project type mcp-server, clone the
sejm-eli-mcp skeleton), tasks with `[P]` markers.
