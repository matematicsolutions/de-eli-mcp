"""German ELI <-> human-readable citation helpers.

Unlike the Polish ELI (which is synthesized from ``{publisher}/{year}/{position}``),
NeuRIS returns a ready ELI string in the ``legislationIdentifier`` field. We parse it,
we do not build it.

ELI string form (schema.org/ELI, FRBR levels):

- expression level (8 segments incl. ``eli``):
  ``eli/{jurisdiction}/{agent}/{year}/{naturalIdentifier}/{pointInTime}/{version}/{language}``
  e.g. ``eli/bund/bgbl-1/2017/s2097/2025-01-01/1/deu``
- work level (5 segments incl. ``eli``):
  ``eli/{jurisdiction}/{agent}/{year}/{naturalIdentifier}``
  e.g. ``eli/bund/bgbl-1/2017/s2097``

The human-readable citation follows the German convention: the official abbreviation
(``abbreviation``, e.g. "BDSG") or the short/long title, plus the publication reference
from ``exampleOfWork.isPartOf.name`` (e.g. "BGBl I, 2017 2097").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_ELI_MARKER = "eli/"


@dataclass(frozen=True)
class EliRef:
    """Structured reference to a German act in NeuRIS / ELI."""

    eli: str  # canonical "eli/..." string (verbatim from the source)
    jurisdiction: str
    agent: str
    year: str
    natural_identifier: str
    point_in_time: str | None = None
    version: str | None = None
    language: str | None = None

    @property
    def eli_uri(self) -> str:
        return self.eli

    @property
    def is_expression(self) -> bool:
        return self.point_in_time is not None

    @property
    def api_path(self) -> str:
        """Path for ``GET /v1/legislation/{eli}``."""
        return f"/v1/legislation/{self.eli}"


def parse_eli(value: str) -> EliRef:
    """Accept an ELI string or an API path and return an ``EliRef``.

    Tolerates: ``eli/bund/...``, ``/eli/bund/...``, the full
    ``/v1/legislation/eli/bund/...`` API path, and a trailing manifestation
    suffix (anything after the language segment is dropped). Raises ``ValueError``
    on unparseable input.
    """
    raw = value.strip()
    idx = raw.find(_ELI_MARKER)
    if idx == -1:
        raise ValueError(
            f"Not a German ELI: {value!r}. Expected e.g. "
            f"'eli/bund/bgbl-1/2017/s2097/2025-01-01/1/deu'."
        )
    eli_part = raw[idx:].strip("/")
    segments = eli_part.split("/")
    # segments[0] == "eli"
    body = segments[1:]
    if len(body) < 4:
        raise ValueError(
            f"Incomplete German ELI: {value!r}. Need at least "
            f"jurisdiction/agent/year/naturalIdentifier."
        )

    jurisdiction, agent, year, natural_identifier = body[0], body[1], body[2], body[3]
    point_in_time = body[4] if len(body) > 4 else None
    version = body[5] if len(body) > 5 else None
    language = body[6] if len(body) > 6 else None

    if language is not None:
        # Drop any manifestation suffix beyond the language segment.
        canonical = "eli/" + "/".join([jurisdiction, agent, year, natural_identifier,
                                       point_in_time or "", version or "", language])
    elif point_in_time is not None:
        canonical = "eli/" + "/".join(
            [jurisdiction, agent, year, natural_identifier]
            + [s for s in (point_in_time, version) if s is not None]
        )
    else:
        canonical = "eli/" + "/".join([jurisdiction, agent, year, natural_identifier])

    return EliRef(
        eli=canonical,
        jurisdiction=jurisdiction,
        agent=agent,
        year=year,
        natural_identifier=natural_identifier,
        point_in_time=point_in_time,
        version=version,
        language=language,
    )


def _publication_reference(payload: dict[str, Any]) -> str | None:
    """Pull the publication reference (e.g. 'BGBl I, 2017 2097') from the payload."""
    work = payload.get("exampleOfWork")
    if isinstance(work, dict):
        part = work.get("isPartOf")
        if isinstance(part, dict):
            name = part.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
    part = payload.get("isPartOf")
    if isinstance(part, dict):
        name = part.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def human_readable_citation(payload: dict[str, Any]) -> str | None:
    """Build a German citation from a Legislation payload.

    Prefers the official abbreviation, falls back to the short/long title, and
    appends the publication reference when available: "BDSG (BGBl I, 2017 2097)".
    """
    label = None
    for key in ("abbreviation", "alternateName", "name"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            label = val.strip()
            break
    if label is None:
        return None
    pub = _publication_reference(payload)
    return f"{label} ({pub})" if pub else label


def source_url(payload: dict[str, Any], base_url: str, eli: str | None = None) -> str:
    """Canonical, independently-openable URL for a legislation record."""
    at_id = payload.get("@id")
    if isinstance(at_id, str) and at_id.strip():
        return f"{base_url}{at_id}"
    if eli:
        return f"{base_url}/v1/legislation/{eli}"
    return base_url


def enrich_legislation_payload(
    payload: dict[str, Any],
    base_url: str,
) -> dict[str, Any]:
    """Attach ``eli_uri`` / ``human_readable_citation`` / ``source_url`` to a payload.

    Does not mutate the input - returns a shallow copy. Tolerates missing fields.
    """
    out = dict(payload)
    eli = payload.get("legislationIdentifier")
    if isinstance(eli, str) and eli.strip():
        out["eli_uri"] = eli.strip()
    citation = human_readable_citation(payload)
    if citation is not None:
        out["human_readable_citation"] = citation
    out["source_url"] = source_url(
        payload, base_url=base_url, eli=out.get("eli_uri") if isinstance(out.get("eli_uri"), str) else None
    )
    return out


def pick_encoding_content_url(
    payload: dict[str, Any],
    fmt: str,
) -> str | None:
    """Return the ``contentUrl`` of the manifestation matching ``fmt`` ('html'|'xml').

    Reads the top-level ``encoding`` array (LegislationObject entries with an
    ``encodingFormat`` such as 'text/html' / 'application/xml').
    """
    wanted = {"html": "text/html", "xml": "application/xml"}.get(fmt)
    if wanted is None:
        return None
    encodings = payload.get("encoding")
    if not isinstance(encodings, list):
        return None
    for enc in encodings:
        if not isinstance(enc, dict):
            continue
        if enc.get("encodingFormat") == wanted:
            url = enc.get("contentUrl")
            if isinstance(url, str) and url.strip():
                return url.strip()
    return None
