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

An MCP server for **NeuRIS** (`rechtsinformationen.bund.de`), Germany's official
federal legal information portal. It searches and retrieves legislation
(Gesetze, Verordnungen) with verifiable ELI identifiers and German citations.

Part of the MateMatic `eu-legal-mcp` production line: the German counterpart of the
Polish `sejm-eli-mcp`, built on the same architecture and citation contract against the
German source.

> **Beta source.** NeuRIS is an official but beta service; its dataset is not yet
> complete. Every response carries a `dataset_note` saying so. For exhaustive
> research, cross-check gesetze-im-internet.de / rechtsprechung-im-internet.de.
>
> **Licence.** German official works - statutes, ordinances, court decisions and
> official headnotes - are outside copyright under § 5 UrhG (gemeinfrei), which is
> the standard basis for reusing German legal data. NeuRIS is operated by the BMJV /
> DigitalService GmbH and publishes no separate API terms or key requirement. This
> connector only relays that public-domain content, with attribution and a
> `source_url`. Caveat: NeuRIS is in test phase; re-check the terms at general
> availability. (This is a practitioner's read, not formal legal advice.)

## The five tools

| Tool | What it does |
|---|---|
| `de_search` | Search legislation by term, ELI and date (`GET /v1/legislation`). |
| `de_get_act` | Fetch act metadata by ELI. |
| `de_get_text` | Fetch the full text (`html` or `xml` / LegalDocML.de). |
| `de_list_publishers` | List the publication organs (BGBl I/II, Bundesanzeiger). |
| `de_recent_changes` | Acts published since a date, newest-first. |

Every response carries the contract: `eli_uri` (e.g. `eli/bund/bgbl-1/2017/s2097/2025-01-01/1/deu`),
`human_readable_citation` (e.g. `BDSG (BGBl I, 2017 2097)`), and `source_url`.

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
- `DE_ELI_CACHE_DIR` - default `~/.matematic/cache/de-eli`
- `DE_ELI_AUDIT_DIR` - default `~/.matematic/audit`

No API key. NeuRIS is keyless.

## Governance

- **Public data only** - read-only against NeuRIS; no client data leaves the machine beyond search parameters.
- **Audit log** - every tool call appends one JSON line to `~/.matematic/audit/de-eli-mcp.jsonl`.
- **Vendor-neutral** - the server talks only to NeuRIS and the local filesystem; no LLM provider, no telemetry.
- **Verifiable citations** - every response is independently checkable via `source_url`.

See `CONSTITUTION.md` (the binding rules) and `DISCOVERY.md` (the NeuRIS API map).

## Tests

```bash
pip install -e ".[dev]"
pytest tests/test_instructions_drift.py -v   # offline
pytest tests/test_smoke.py -v                # hits live NeuRIS
```

## Licence

Apache-2.0. © Matematic Solutions / Wieslaw Mazur.
