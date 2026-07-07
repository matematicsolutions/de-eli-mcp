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

(Budowanie ze źródeł — niżej.)

An MCP server for German federal law: **NeuRIS** (`rechtsinformationen.bund.de`) for
legislation, plus two case-law sources - NeuRIS's beta case-law slice, and the
**complete** federal-courts aggregator **rechtsprechung-im-internet.de** (RII, official
BMJ/juris portal) for **BVerfG, BGH, BAG, BFH, BVerwG, BSG** (+ BPatG).

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
> **Licence.** German official works - statutes, ordinances, court decisions and
> official headnotes - are outside copyright under § 5 UrhG (gemeinfrei), which is
> the standard basis for reusing German legal data. NeuRIS is operated by the BMJV /
> DigitalService GmbH; RII is operated by the BMJ (juris GmbH). Neither publishes a
> separate API terms or key requirement. This connector only relays that public-domain
> content, with attribution and a `source_url`. Caveat: NeuRIS is in test phase;
> re-check the terms at general availability. (This is a practitioner's read, not
> formal legal advice.)

## The seven tools

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
- `DE_ELI_CACHE_DIR` - default `~/.matematic/cache/de-eli`
- `DE_ELI_AUDIT_DIR` - default `~/.matematic/audit`

No API key. Both NeuRIS and RII are keyless.

## Governance

- **Public data only** - read-only against NeuRIS; no client data leaves the machine beyond search parameters.
- **Audit log** - every tool call appends one JSON line to `~/.matematic/audit/de-eli-mcp.jsonl`.
- **Vendor-neutral** - the server talks only to NeuRIS and the local filesystem; no LLM provider, no telemetry.
- **Verifiable citations** - every response is independently checkable via `source_url`.

See `CONSTITUTION.md` (the binding rules) and `DISCOVERY.md` (the NeuRIS API map).

## Tests

```bash
pip install -e ".[dev]"
pytest tests/test_instructions_drift.py tests/test_rii_client.py -v   # offline (fixtures)
pytest tests/test_smoke.py -v                                        # hits live NeuRIS + RII
```

## Licence

Apache-2.0. © Matematic Solutions / Wieslaw Mazur.
