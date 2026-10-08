# de-eli-mcp - Claude plugin

German federal law with verifiable citations, as a Claude plugin. It runs the
[de-eli-mcp](https://github.com/matematicsolutions/de-eli-mcp) MCP server, version 0.5.4
from PyPI. `server/uv.lock` pins that package and every dependency with hashes, and the
plugin starts it with `uv run --frozen`, so it runs exactly what was reviewed. Every
answer carries the official source and identifier (ELI for legislation, ECLI or docket
number for decisions), so a citation can be checked instead of trusted.

What it covers: federal legislation from the federal legal information portal (NeuRIS,
still on its `testphase` host), case law from the federal courts
(rechtsprechung-im-internet.de) and from all court levels via Open Legal Data, and
Bundestag and Bundesrat documents and procedures (DIP). The full tool list and the source
notes are in the [main README](https://github.com/matematicsolutions/de-eli-mcp#readme)
and [SOURCES.md](https://github.com/matematicsolutions/de-eli-mcp/blob/main/SOURCES.md).

## Requirements

Claude Code or the Claude desktop app, and [uv](https://docs.astral.sh/uv/) on your
machine (it installs the locked packages on first start and runs the server).

## Install

```
/plugin marketplace add matematicsolutions/de-eli-mcp
/plugin install de-eli-mcp@de-eli-mcp
```

## Data

The server runs on your machine. Each tool call sends your query to the public German
source it names (NeuRIS at rechtsinformationen.bund.de, rechtsprechung-im-internet.de,
Open Legal Data or the Bundestag DIP API) and to nothing else; nothing goes to MateMatic.
DIP requests use the public API key that the Bundestag publishes for general use. Your
query and the results also pass through whatever model you use, the same way as any
other message.

The standalone server can fetch a small configuration file (updated source addresses) from
this repository's GitHub Releases on first use. The plugin turns that off
(`DE_ELI_RUNTIME_URL` set to empty in `plugin.json`), so it runs only the reviewed code with
its built-in source addresses and makes no request other than the tool calls above.

Two things are written locally, in your home directory:

- a response cache (`~/.matematic/cache/de-eli`), so a repeated lookup does not hit
  the source again. Court decisions are public records and can name the parties.
- an audit log (`~/.matematic/audit/de-eli-mcp.jsonl`), one line per tool call: the
  tool name, a SHA-256 hash of the input (not the input itself), result size, time
  and status.

Delete either folder at any time; `DE_ELI_CACHE_DIR` and `DE_ELI_AUDIT_DIR` move them.

## Licence

Apache-2.0, see the repository's [LICENSE](https://github.com/matematicsolutions/de-eli-mcp/blob/main/LICENSE).
Source data terms are in [SOURCES.md](https://github.com/matematicsolutions/de-eli-mcp/blob/main/SOURCES.md).
