"""JSONL audit logger for AI Act art. 12.

Every call to every MCP tool writes one JSON line to:

    ~/.matematic/audit/de-eli-mcp.jsonl

(or to the directory given by ``DE_ELI_AUDIT_DIR``).

Line: ``{ts, tool, input_hash, output_count_or_size, duration_ms, status}``.

If the write fails, the tool returns an error instead of silently continuing
(Art. 2 CONSTITUTION.md). Inherited verbatim from sejm-eli-mcp.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

Status = Literal["ok", "error"]

_AUDIT_FILENAME = "de-eli-mcp.jsonl"


def _resolve_audit_dir() -> Path:
    env = os.environ.get("DE_ELI_AUDIT_DIR")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".matematic" / "audit"


def hash_input(payload: Any) -> str:
    """SHA-256 of a stable JSON serialization of the input.

    Sorts keys and compacts separators - two equivalent dictionaries
    produce the same hash. No raw query text is stored.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AuditLogger:
    """Append-only JSONL logger."""

    def __init__(self, audit_dir: Path | None = None) -> None:
        self._dir = (audit_dir or _resolve_audit_dir()).expanduser()
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / _AUDIT_FILENAME

    @property
    def path(self) -> Path:
        return self._path

    def log(
        self,
        *,
        tool: str,
        input_hash: str,
        output_count_or_size: int,
        duration_ms: int,
        status: Status,
        error: str | None = None,
    ) -> None:
        record: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "tool": tool,
            "input_hash": input_hash,
            "output_count_or_size": output_count_or_size,
            "duration_ms": duration_ms,
            "status": status,
        }
        if error is not None:
            record["error"] = error[:500]  # trim - the audit log stays light
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        # If this fails, it fails (Art. 2 CONSTITUTION).
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(line)


class _Timer:
    """Context-managed timer in milliseconds."""

    def __init__(self) -> None:
        self._t0 = 0.0
        self.duration_ms = 0

    def __enter__(self) -> "_Timer":
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.duration_ms = int((time.perf_counter() - self._t0) * 1000)


def timer() -> _Timer:
    return _Timer()
