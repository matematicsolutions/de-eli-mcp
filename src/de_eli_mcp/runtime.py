"""Lazy runtime manifest - externalizes VOLATILE config (upstream base URLs,
citation-grammar version) out of the shipped package.

Why this exists
---------------
Upstream endpoints move (e.g. the NeuRIS API still lives on a ``testphase``
host that will become production) and citation grammars get revised. Baking
those into the package means a dead endpoint needs a full PyPI release to fix.
Instead we pull a tiny static ``de-runtime.json.gz`` from THIS repo's GitHub
Release on first use; editing ``runtime/de-runtime.json`` + re-running the
release workflow repoints every client WITHOUT a package release
("popraw przez kontekst, nie deploy").

Local-first / RODO
------------------
The manifest is a static asset from GitHub's CDN - same trust model as
``pip install``. Zero query content leaves the machine, it is cached under the
user cache dir, and ANY failure (offline, 404, bad payload) falls back to the
hardcoded defaults in each client module, so the server never breaks and works
offline after (or even without) the first fetch.

Activation meter (side-effect, not a tracking pixel)
----------------------------------------------------
The asset URL is constructed ONLY here at runtime - it appears in no README,
sitemap or page, so a crawler cannot guess it. Its GitHub ``download_count`` is
therefore a clean count of real first-use activations, fleet-wide, with zero
new infrastructure. The pull has genuine operational value (repointing), so the
measurement is a side-effect of a good decision, not a bolted-on beacon.

Opt-out: set ``DE_ELI_RUNTIME_URL=""`` to disable the fetch entirely.
"""

from __future__ import annotations

import gzip
import json
import os
import urllib.request
from pathlib import Path
from typing import Any

# Unlinked asset - referenced only from code (see module docstring). Overridable
# for testing / air-gapped mirrors; empty string disables the fetch.
MANIFEST_URL = os.environ.get(
    "DE_ELI_RUNTIME_URL",
    "https://github.com/matematicsolutions/de-eli-mcp/releases/latest/download/de-runtime.json.gz",
)
_CACHE_NAME = "de-runtime.json"
_TIMEOUT = 15
_USER_AGENT = "de-eli-mcp-runtime (+https://github.com/matematicsolutions/de-eli-mcp)"

_runtime: dict[str, Any] | None = None


def _cache_dir() -> Path:
    # Mirrors HttpCache._resolve_cache_dir so both share one location.
    env = os.environ.get("DE_ELI_CACHE_DIR")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".matematic" / "cache" / "de-eli"


def _load_cached() -> "dict[str, Any] | None":
    try:
        p = _cache_dir() / _CACHE_NAME
        if p.is_file():
            data = json.loads(p.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
    except Exception:
        pass
    return None


def _fetch_and_cache() -> "dict[str, Any]":
    if not MANIFEST_URL:  # explicit opt-out
        return {}
    try:
        req = urllib.request.Request(MANIFEST_URL, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310
            raw = resp.read()
        data = json.loads(gzip.decompress(raw).decode("utf-8"))
        if not isinstance(data, dict):
            return {}
        try:  # best-effort persist for offline fallback
            d = _cache_dir()
            d.mkdir(parents=True, exist_ok=True)
            (d / _CACHE_NAME).write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            pass
        return data
    except Exception:
        return {}  # offline / 404 / malformed -> hardcoded defaults win


def get_runtime() -> "dict[str, Any]":
    """Return the runtime manifest, fetched once per process.

    Network-first (so an endpoint repoint reaches clients on next start), with
    the on-disk cache as the offline fallback, and finally ``{}`` so callers use
    their hardcoded defaults. Never raises.
    """
    global _runtime
    if _runtime is not None:
        return _runtime
    data = _fetch_and_cache()
    if not data:
        data = _load_cached() or {}
    _runtime = data
    return _runtime


def base_url(key: str, default: str) -> str:
    """Runtime-manifest base URL for an upstream (``eli``/``rii``/``oldp``/``dip``),
    or ``default`` when the manifest is missing/incomplete."""
    urls = get_runtime().get("base_urls")
    if isinstance(urls, dict):
        val = urls.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return default
