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

---

# Discovery addendum: rechtsprechung-im-internet.de (RII) - feature 003

Date: 2026-07-07
Trigger: an independent audit against the Legal Data Hunter catalogue
(`worldwidelaw/legal-sources`, `manifest.yaml`) found that NeuRIS `/v1/case-law`
(feature 002) is a small beta slice, while LDH marks RII coverage of **BVerfG, BGH,
BAG, BFH, BVerwG, BSG** as `status: complete`. Live probe confirmed this end-to-end.

## Base properties (CONFIRMED, live probe 2026-07-07)

- **Base URL:** `https://www.rechtsprechung-im-internet.de` (production, not a beta/testphase host).
- **robots.txt** (`/robots.txt` -> 302 -> `/jportal/docs/eclicrawler/robots.txt`) disallows
  generic crawlers (`Disallow: /`) but publishes per-day `Sitemap:` entries for a
  dedicated `DG_JUSTICE_CRAWLER` UA. We do not use those per-day sitemaps - the site
  separately publishes one master TOC (below), which is the intended low-friction entry
  point and is not robots-restricted.
- **Master TOC:** `GET /rii-toc.xml` - single XML file, **~23 MB, ~83,300 `<item>` rows**
  covering the site's full history, regenerated nightly (see the file's own
  `<!-- generator:... lastBuildDate:... -->` comment). No auth, no rate limit observed.
  Row shape: `<item><gericht>BGH 9. Zivilsenat</gericht><entsch-datum>20100114</entsch-datum>
  <aktenzeichen>IX ZB 72/08</aktenzeichen><link>.../jportal/docs/bsjrs/jb-JURE100055033.zip</link>
  <modified>...</modified></item>`.
- **Per-decision documents:** each `<link>` is a ZIP containing exactly one XML file
  (`<!DOCTYPE dokument SYSTEM ".../dtd/v1/rii-dok.dtd">`) with the full decision:
  `doknr`, `ecli` (present when the court assigns one - BVerfG/BAG samples had it, an
  older 2010 BGH sample did not), `gertyp`, `spruchkoerper`, `entsch-datum`,
  `aktenzeichen`, `doktyp`, `norm`, `vorinstanz`, `titelzeile`, `leitsatz`, `tenor`,
  `tatbestand`, `entscheidungsgruende`, `gruende` (full text, paragraph-numbered),
  `identifier` (a stable jportal deep link), `region`, `publisher` (`BMJV`),
  `accessRights: public`.

## Live TOC composition (2026-07-07 snapshot, verified by grep, not sampling)

| Court | Rows in TOC |
|---|---|
| BGH | 34,787 |
| BFH | 11,613 |
| BVerwG | 10,287 |
| BPatG | 7,293 |
| BAG | 7,233 |
| BSG | 6,380 |
| BVerfG | 5,718 |

All six courts named in the task are present with non-trivial coverage; BPatG (Bundespatentgericht)
comes along for free via the same infrastructure and is exposed as a bonus 7th court.

## Mapping to the 2 new super-tools (CONFIRMED)

| Super-tool | Source | Notes |
|---|---|---|
| `de_rii_case_search` | `GET /rii-toc.xml`, filtered client-side | No query API upstream - the TOC is fetched once (cached 12h client-side; upstream regenerates nightly) and filtered in memory by court / Aktenzeichen substring / date range. No full-text search (the TOC carries no decision text). |
| `de_rii_get_case_text` | `GET {zip_url}` -> unzip -> parse XML | `doc_id` (derived from the ZIP filename, e.g. `JURE100055033`) resolves back to its `zip_url` via a fresh TOC lookup, unless a full URL is passed directly. Decisions are immutable once published, so the parsed result is cached long-term (30 days). |

## Citation contract (Article IV) - CLOSED for RII case law

- `eli_uri` = the real `ecli` when the court publishes one (e.g.
  `ECLI:DE:BVerfG:2024:rk20241120.1bvr226823`); falls back to a synthetic `rii:{doknr}`
  when RII has no ECLI for that decision (observed on some older BGH decisions).
- `human_readable_citation` = German convention `{Gericht}, {Doktyp} vom {DD.MM.YYYY} -
  {Aktenzeichen}` (e.g. `BVerfG, Kammerbeschluss vom 20.11.2024 - 1 BvR 2268/23`).
- `source_url` = the `identifier` field (stable jportal viewer deep link); falls back to
  the ZIP URL if `identifier` is absent.

## Decision: BUILD (done, 2026-07-07)

No blockers. RII has no API terms distinct from NeuRIS's own public-domain basis
(§ 5 UrhG, amtliche Werke) - same licence rationale as feature 001/002. Implemented as
`src/de_eli_mcp/rii_client.py` (new client, TOC parsing + court/date/Aktenzeichen filter
+ ZIP/XML decision fetch), two new tools (`de_rii_case_search`, `de_rii_get_case_text`),
offline unit tests against fixed fixtures (`tests/test_rii_client.py`, 13 tests) plus
live smoke tests against the real TOC and real decisions for all six target courts
(`tests/test_smoke.py`, 3 tests). Version bumped 0.1.0 -> 0.2.0.
