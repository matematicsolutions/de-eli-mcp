# de-eli-mcp

<!-- mcp-name: io.github.matematicsolutions/de-eli-mcp -->


## Instalacja (jedna komenda)

Opublikowany na PyPI + MCP Registry (`io.github.matematicsolutions/de-eli-mcp`). Uruchomienie bez klonowania:

```bash
uvx de-eli-mcp
```

Konfiguracja klienta MCP (stdio):

```json
{ "mcpServers": { "de-eli-mcp": { "command": "uvx", "args": ["de-eli-mcp"] } } }
```

### Windows 11 ze Smart App Control

Smart App Control blokuje niepodpisane pliki wykonywalne, a `uvx.exe`, `pip.exe`
i generowane przy instalacji entry-pointy (`de-eli-mcp.exe`) podpisane nie są.
`python.exe` z python.org jest podpisany przez Python Software Foundation, więc
uruchomienie przez moduł omija blokadę:

```bash
python -m pip install de-eli-mcp
python -m de_eli_mcp
```

```json
{ "mcpServers": { "de-eli-mcp": { "command": "python", "args": ["-m", "de_eli_mcp"] } } }
```

Uwaga: `pip install` (przez `pip.exe`) też bywa blokowany - stąd `python -m pip`.
Nie wyłączaj Smart App Control, żeby to obejść: wyłączenie jest **nieodwracalne**
bez ponownej instalacji systemu.

(Budowanie ze źródeł — niżej.)

An MCP server for German law: **NeuRIS** (`rechtsinformationen.bund.de`) for federal
legislation, three case-law sources - NeuRIS's beta case-law slice, the **complete**
federal-courts aggregator **rechtsprechung-im-internet.de** (RII, official BMJ/juris
portal) for **BVerfG, BGH, BAG, BFH, BVerwG, BSG** (+ BPatG), and **Open Legal Data**
(`de.openlegaldata.io`, ~424k decisions from ~1 100 courts of ALL levels, including
the state courts of all 16 Laender, with full-text search) - plus the Bundestag's
**DIP** (`dip.bundestag.de`) for parliamentary documents and legislative history
(~287k Drucksachen with full text, plenary transcripts, ~335k legislative procedures,
Bundestag AND Bundesrat).

Part of the MateMatic `eu-legal-mcp` production line: the German counterpart of the
Polish `sejm-eli-mcp`, built on the same architecture and citation contract against the
German source.

> **Beta source (legislation + `de_case_search`).** NeuRIS is an official but beta
> service; its dataset is not yet complete. Every response carries a `dataset_note`
> saying so.
>
> **Complete source (case law).** `de_rii_case_search` / `de_rii_get_case_text` query
> rechtsprechung-im-internet.de directly. Per an independent audit (Legal Data Hunter,
> `worldwidelaw/legal-sources`), RII's coverage of BVerfG, BGH, BAG, BFH, BVerwG and BSG
> is marked `status: complete` - unlike NeuRIS's `/v1/case-law`, which only carries a
> small beta slice (and can drop fields such as `ecli` for the very same decision RII
> serves with a full ECLI - see BAG decision `KARE600069049` / `ECLI:DE:BAG:2024:...` as
> a live example). **Prefer the RII tools for these six courts.**
>
> **State courts + full-text search (Open Legal Data).** `de_oldp_case_search` /
> `de_oldp_get_case` query de.openlegaldata.io - a community open-data aggregator
> (Open Knowledge Foundation ecosystem, BMBF Prototypefund) of ~424k decisions from
> ~1 100 German courts at every level, including the state courts of all 16 Laender.
> It is NOT an official government service and does not claim completeness - for the
> six federal supreme courts prefer the RII tools; use OLDP for state case law and
> for full-text hunting (no other source here searches decision content).
>
> **Legislative history (Bundestag DIP).** `de_dip_search` / `de_dip_get_document`
> query the parliament's official DIP API - Drucksachen (bills, motions, committee
> reports, government answers - the home of Gesetzesbegruendungen), plenary
> transcripts and legislative procedures, for Bundestag and Bundesrat. The Bundestag
> publishes a public API key on its help page (the current one is valid until end of
> May 2027 and ships as the default); set `DE_DIP_API_KEY` when it rotates or to use
> your own key.
>
> **Licence.** German official works - statutes, ordinances, court decisions and
> official headnotes - are outside copyright under § 5 UrhG (gemeinfrei), which is
> the standard basis for reusing German legal data. NeuRIS is operated by the BMJV /
> DigitalService GmbH; RII is operated by the BMJ (juris GmbH). Neither publishes a
> separate API terms or key requirement. Open Legal Data's database is under ODbL
> v1.0 (the decisions themselves are gemeinfrei); DIP data is under Data licence
> Germany - attribution - 2.0 (dl-de/by-2-0). This connector only relays that
> public content, with attribution and a `source_url`. Caveat: NeuRIS is in test
> phase; re-check the terms at general availability. (This is a practitioner's
> read, not formal legal advice.)

## The tools

| Tool | What it does |
|---|---|
| `de_search` | Search legislation by term, ELI and date (`GET /v1/legislation`). |
| `de_get_act` | Fetch act metadata by ELI. |
| `de_get_text` | Fetch the full text (`html` or `xml` / LegalDocML.de). |
| `de_list_publishers` | List the publication organs (BGBl I/II, Bundesanzeiger). |
| `de_recent_changes` | Acts published since a date, newest-first. |
| `de_case_search` / `de_get_decision(_text)` | NeuRIS case-law beta slice (`/v1/case-law`). |
| `de_rii_case_search` | Search **BVerfG/BGH/BAG/BFH/BVerwG/BSG/BPatG** decisions via RII's master TOC (court, Aktenzeichen substring, date range). |
| `de_rii_get_case_text` | Full text of one RII decision by `doc_id` - real `ecli` when the court publishes one, plus `titelzeile`/`leitsatz`/`tenor`/full `content`. |
| `de_oldp_case_search` | Search **Open Legal Data** - 423 944 decisions from 1 119 courts at all levels (verified live 2026-07-08), the only tool here covering **state courts** and offering **full-text search** (`text`). Metadata filters: `court_slug`, `file_number` (exact), `date_after`/`date_before`. |
| `de_oldp_get_case` | Full decision text (HTML) by OLDP id or slug, with ECLI when the source carries one. |
| `de_dip_search` | Search the Bundestag **DIP** - Drucksachen (287 327), Plenarprotokolle (5 789), Vorgaenge (334 524); filters `titel`, `dokumentnummer`, `zuordnung` (BT/BR), `wahlperiode`, dates; cursor pagination. |
| `de_dip_get_document` | One DIP entity by id; the `-text` resource variants return the full document text. Citations like `BT-Drs. 20/1` with the official PDF as `source_url`. |

Every response carries the contract: `eli_uri` (ELI e.g. `eli/bund/bgbl-1/2017/s2097/2025-01-01/1/deu`,
or ECLI for RII case law e.g. `ECLI:DE:BVerfG:2024:rk20241120.1bvr226823`),
`human_readable_citation` (e.g. `BDSG (BGBl I, 2017 2097)` or
`BVerfG, Kammerbeschluss vom 20.11.2024 - 1 BvR 2268/23`), and `source_url`.

## Install

```bash
cd de-eli-mcp
pip install -e .
```

## Configure (Claude Code / any MCP client)

Copy `.mcp.json.example` and adjust if needed:

```json
{
  "mcpServers": {
    "de-eli-mcp": { "command": "de-eli-mcp" }
  }
}
```

Environment:

- `DE_ELI_BASE_URL` - default `https://testphase.rechtsinformationen.bund.de`
- `DE_RII_BASE_URL` - default `https://www.rechtsprechung-im-internet.de`
- `DE_OLDP_BASE_URL` - default `https://de.openlegaldata.io`
- `DE_DIP_BASE_URL` - default `https://search.dip.bundestag.de`
- `DE_DIP_API_KEY` - default: the public key the Bundestag documents on
  `dip.bundestag.de/über-dip/hilfe/api` (valid until end of May 2027; rotates ~yearly)
- `DE_ELI_CACHE_DIR` - default `~/.matematic/cache/de-eli`
- `DE_ELI_AUDIT_DIR` - default `~/.matematic/audit`

NeuRIS, RII and Open Legal Data are keyless. DIP needs an API key, but the Bundestag
publishes a public one (shipped as the default) - zero setup either way.

## Governance

- **Public data only** - read-only against NeuRIS; no client data leaves the machine beyond search parameters.
- **Audit log** - every tool call appends one JSON line to `~/.matematic/audit/de-eli-mcp.jsonl`.
- **Vendor-neutral** - the server talks only to NeuRIS and the local filesystem; no LLM provider, no telemetry.
- **Verifiable citations** - every response is independently checkable via `source_url`.

See `CONSTITUTION.md` (the binding rules) and `DISCOVERY.md` (the NeuRIS API map).

## Tests

```bash
pip install -e ".[dev]"
# offline (fixtures)
pytest tests/test_instructions_drift.py tests/test_rii_client.py tests/test_oldp_client.py tests/test_dip_client.py -v
# live smokes (NeuRIS + RII + Open Legal Data + DIP)
pytest tests/test_smoke.py -v
```

## Licence

Apache-2.0. © Matematic Solutions / Wieslaw Mazur.
