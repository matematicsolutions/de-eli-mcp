# Constitution of de-eli-mcp

Version: 0.1.0
Date: 2026-06-24
Licence: Apache-2.0

`de-eli-mcp` is an MCP server for the German legal portal NeuRIS (`rechtsinformationen.bund.de`)
provided by the Bundesministerium der Justiz / Bundesamt fur Justiz. It searches and retrieves German
normative acts (Gesetze, Verordnungen) with verifiable citations. The MVP covers legislation; federal
court case law (Rechtsprechung, ECLI identifier) is phase 2 - the same NeuRIS API, a separate sub-family
of tools.

The 4 principles below are inherited from the `eu-legal-mcp` line Constitution (Article IV).

---

## Art. 1. Public data only

`https://testphase.rechtsinformationen.bund.de` (NeuRIS, beta phase) is the official, public source of
German normative acts. Legal status of the data: German official works (statutes, ordinances, court
decisions and official headnotes) are outside copyright under § 5 UrhG (gemeinfrei). NeuRIS is operated
by the BMJV / DigitalService GmbH and (as of the beta) publishes no separate API terms or key requirement
- reuse rests on § 5 UrhG. **Residual watch-item:** re-check the terms at general availability, as the
beta service may formalize usage conditions.

This server must not transfer client personal data or pleadings to the API (read-only for the source's
data), nor proxy access to other databases.

## Art. 2. Mandatory audit log

Every call to every MCP tool MUST be written to `~/.matematic/audit/de-eli-mcp.jsonl` as one JSON line
(ts / tool / input_hash SHA-256 / output_count_or_size / duration_ms / status). Inability to write = the
tool returns an error, it does not silently skip.

## Art. 3. Vendor neutrality

No tool hardcodes an LLM provider, assumes a model, or introduces commercial telemetry. The server
communicates only with the NeuRIS API and the local filesystem. Authentication: **no API key** (confirmed
from the OpenAPI; own backoff + cache despite no documented rate-limit).

## Art. 4. ELI/ECLI citations and a human-readable citation are mandatory

Every response MUST contain three fields:
- `eli_uri` (legislation) or `ecli` (case law, phase 2): the canonical identifier. **NeuRIS exposes ELI
  directly** (field `legislationIdentifier`, FRBR model; confirmed from the OpenAPI) - Article IV is met
  with no compromise.
- `human_readable_citation`: a citation in the German convention (e.g. "§ 433 BGB"; "BGBl. I 1979 S. 1325").
- `source_url`: a full URL to the document on rechtsinformationen.bund.de.

---

## Open points (do not block the build)

1. NeuRIS data licence / re-use terms (see Art. 1) - confirm before public distribution.
2. Beta - incomplete dataset. `de_get_*` must return an explicit completeness note; consider a fallback to
   gesetze-im-internet.de (XML) as a backup source. Ties into the "freshness / fail-loud = first-class
   feature" rule.
3. No documented rate-limit - own backoff + cache regardless.

## Constitution evolution

Changes to art. 1-4 follow SEMVER + an entry in `CHANGELOG.md` + a `pyproject.toml` bump.

First version: 2026-06-24. Author: Wieslaw Mazur / MateMatic.
