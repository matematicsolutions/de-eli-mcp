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
    eli_val = out.get("eli_uri")
    out["source_url"] = source_url(
        payload, base_url=base_url, eli=eli_val if isinstance(eli_val, str) else None
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


# --- Case law (ECLI) ---------------------------------------------------------


def _format_iso_date_de(iso: str | None) -> str | None:
    """'2024-06-20' -> '20.06.2024' (German date convention)."""
    if not isinstance(iso, str) or len(iso) < 10:
        return None
    y, m, d = iso[:4], iso[5:7], iso[8:10]
    if y.isdigit() and m.isdigit() and d.isdigit():
        return f"{d}.{m}.{y}"
    return None


def decision_human_readable_citation(payload: dict[str, Any]) -> str | None:
    """German case-law citation, e.g. 'BAG, Urteil vom 20.06.2024 - 8 AZR 124/23'."""
    court = None
    for key in ("courtType", "courtName"):
        v = payload.get(key)
        if isinstance(v, str) and v.strip():
            court = v.strip()
            break
    doc_type = payload.get("documentType")
    date_de = _format_iso_date_de(payload.get("decisionDate"))
    file_no = None
    files = payload.get("fileNumbers")
    if isinstance(files, list) and files and isinstance(files[0], str):
        file_no = files[0].strip()

    head = ", ".join(p for p in (court, doc_type if isinstance(doc_type, str) else None) if p)
    parts = [p for p in (head or None, f"vom {date_de}" if date_de else None) if p]
    citation = " ".join(parts) if parts else None
    if citation and file_no:
        return f"{citation} - {file_no}"
    return citation or file_no


def enrich_decision_payload(payload: dict[str, Any], base_url: str) -> dict[str, Any]:
    """Attach ``ecli`` / ``human_readable_citation`` / ``source_url`` to a decision payload."""
    out = dict(payload)
    ecli = payload.get("ecli")
    if isinstance(ecli, str) and ecli.strip():
        out["ecli"] = ecli.strip()
    citation = decision_human_readable_citation(payload)
    if citation is not None:
        out["human_readable_citation"] = citation
    at_id = payload.get("@id")
    out["source_url"] = (
        f"{base_url}{at_id}" if isinstance(at_id, str) and at_id.strip() else base_url
    )
    return out


# --- Case law via rechtsprechung-im-internet.de (RII) -------------------------


def rii_human_readable_citation(payload: dict[str, Any]) -> str | None:
    """German case-law citation from an RII decision dict (``parse_decision_xml`` output),
    e.g. ``'BVerfG, Beschluss vom 20.11.2024 - 1 BvR 2268/23'``.

    Convention: {Gericht}, {Doktyp} vom {DD.MM.YYYY} - {Aktenzeichen}. Falls back
    gracefully if a field is missing (still returns whatever is available).
    """
    court = payload.get("gertyp")
    doktyp = payload.get("doktyp")
    date_de = _format_iso_date_de(_rii_date_to_iso(payload.get("entsch_datum")))
    aktenzeichen = payload.get("aktenzeichen")

    head = ", ".join(p for p in (court, doktyp) if isinstance(p, str) and p.strip())
    parts = [p for p in (head or None, f"vom {date_de}" if date_de else None) if p]
    citation = " ".join(parts) if parts else None
    if citation and aktenzeichen:
        return f"{citation} - {aktenzeichen}"
    return citation or aktenzeichen


def _rii_date_to_iso(raw: str | None) -> str | None:
    """RII dates are 'YYYYMMDD' (no separators); convert to ISO 'YYYY-MM-DD'."""
    if not isinstance(raw, str) or len(raw) != 8 or not raw.isdigit():
        return None
    return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"


def rii_source_url(payload: dict[str, Any], fallback_zip_url: str | None = None) -> str:
    """Canonical, independently-openable URL for an RII decision.

    Prefers the ``identifier`` field (a stable jportal deep link into the RII viewer);
    falls back to the ZIP URL the document was fetched from.
    """
    identifier = payload.get("identifier")
    if isinstance(identifier, str) and identifier.strip():
        return identifier.strip()
    zip_url = fallback_zip_url or payload.get("_source_zip_url")
    if isinstance(zip_url, str) and zip_url.strip():
        return zip_url.strip()
    return "https://www.rechtsprechung-im-internet.de"


def enrich_rii_decision(payload: dict[str, Any]) -> dict[str, Any]:
    """Attach ``eli_uri`` (ECLI when present, else RII doknr-based URI),
    ``human_readable_citation`` and ``source_url`` to an RII decision dict.
    """
    out = dict(payload)
    ecli = payload.get("ecli")
    out["eli_uri"] = (
        ecli.strip() if isinstance(ecli, str) and ecli.strip() else None
    ) or f"rii:{payload.get('doknr', 'unknown')}"
    out["human_readable_citation"] = rii_human_readable_citation(payload)
    out["source_url"] = rii_source_url(payload)
    return out
