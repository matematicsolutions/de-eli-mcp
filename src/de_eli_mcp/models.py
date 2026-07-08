"""Pydantic v2 models for the NeuRIS API + de-eli-mcp.

Models are deliberately tolerant (``extra="allow"``) - NeuRIS is in beta and may add
fields; we do not want validation to break on new attributes. The NeuRIS payload is
JSON-LD (schema.org/Legislation, Hydra collections).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SortBy = Literal["date", "temporalCoverageFrom", "legislationIdentifier"]
SortDir = Literal["asc", "desc"]
TextFormat = Literal["html", "xml"]

# NeuRIS is a beta service; its dataset is explicitly incomplete. We surface this on
# every output (the "fail-loud / freshness" rule) rather than implying full coverage.
DATASET_NOTE = (
    "NeuRIS is a beta service and its dataset is not yet complete. For exhaustive "
    "research cross-check gesetze-im-internet.de / rechtsprechung-im-internet.de."
)


class _Tolerant(BaseModel):
    """Base for models that accept unforeseen fields."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


# --- NeuRIS primitives -------------------------------------------------------


class ActInfo(_Tolerant):
    """Lightweight legislation record - from a listing / search item."""

    id: str | None = Field(default=None, alias="@id")
    name: str | None = None
    abbreviation: str | None = None
    alternateName: str | None = None
    legislationIdentifier: str | None = None
    legislationLegalForce: str | None = None

    # Enrichments added by our server (Art. 4 CONSTITUTION).
    eli_uri: str | None = None
    human_readable_citation: str | None = None
    source_url: str | None = None


class Act(_Tolerant):
    """Full legislation record - GET /v1/legislation/{eli}.

    Keeps the structural tree (``hasPart``) and manifestations (``encoding``) as
    extra fields; the typed fields below are the ones the contract depends on.
    """

    id: str | None = Field(default=None, alias="@id")
    name: str | None = None
    abbreviation: str | None = None
    alternateName: str | None = None
    legislationIdentifier: str | None = None
    legislationLegalForce: str | None = None

    eli_uri: str | None = None
    human_readable_citation: str | None = None
    source_url: str | None = None
    dataset_note: str = DATASET_NOTE


# --- Tool I/O ----------------------------------------------------------------


class SearchQuery(_Tolerant):
    """Arguments for the ``de_search`` tool."""

    search_term: str | None = Field(default=None, alias="searchTerm")
    eli: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    temporal_coverage_from: str | None = None
    temporal_coverage_to: str | None = None
    size: int = Field(default=20, ge=1, le=300)
    page_index: int = Field(default=0, ge=0)
    sort: SortBy | None = None
    sort_dir: SortDir | None = None


class SearchResult(_Tolerant):
    """Result of ``de_search``."""

    total_items: int
    items: list[ActInfo] = Field(default_factory=list)
    query_echo: SearchQuery | None = None
    dataset_note: str = DATASET_NOTE


class ActText(_Tolerant):
    """Result of ``de_get_text``."""

    eli_uri: str
    human_readable_citation: str | None = None
    source_url: str
    format: TextFormat
    content: str | None = None
    content_type: str | None = None
    byte_size: int | None = None
    dataset_note: str = DATASET_NOTE


class Publisher(_Tolerant):
    """A NeuRIS publication organ (derived from ELI ``agent`` codes)."""

    code: str
    name: str | None = None
    note: str | None = None


# --- Case law (ECLI) ---------------------------------------------------------


class DecisionInfo(_Tolerant):
    """Lightweight court-decision record - from a case-law search item."""

    id: str | None = Field(default=None, alias="@id")
    documentNumber: str | None = None
    ecli: str | None = None
    headline: str | None = None
    decisionDate: str | None = None
    fileNumbers: list[str] = Field(default_factory=list)
    courtType: str | None = None
    courtName: str | None = None
    documentType: str | None = None

    # Enrichments (Art. 4 CONSTITUTION). The canonical id for case law is the ECLI.
    human_readable_citation: str | None = None
    source_url: str | None = None


class Decision(DecisionInfo):
    """Full court-decision metadata - GET /v1/case-law/{documentNumber}."""

    dataset_note: str = DATASET_NOTE


class CaseSearchQuery(_Tolerant):
    """Arguments for the ``de_case_search`` tool."""

    search_term: str | None = Field(default=None, alias="searchTerm")
    date_from: str | None = None
    date_to: str | None = None
    size: int = Field(default=20, ge=1, le=300)
    page_index: int = Field(default=0, ge=0)
    sort: str | None = None


class CaseSearchResult(_Tolerant):
    """Result of ``de_case_search``."""

    total_items: int
    items: list[DecisionInfo] = Field(default_factory=list)
    query_echo: CaseSearchQuery | None = None
    dataset_note: str = DATASET_NOTE


class DecisionText(_Tolerant):
    """Result of ``de_get_decision_text``."""

    ecli: str | None = None
    human_readable_citation: str | None = None
    source_url: str
    format: TextFormat
    content: str | None = None
    content_type: str | None = None
    byte_size: int | None = None
    dataset_note: str = DATASET_NOTE


# --- Case law via rechtsprechung-im-internet.de (RII) -------------------------

RII_NOTE = (
    "Source: rechtsprechung-im-internet.de (RII), the official BMJ/juris case-law "
    "aggregator. Coverage per the Legal Data Hunter audit (worldwidelaw/legal-sources): "
    "BVerfG, BGH, BAG, BFH, BVerwG, BSG (+ BPatG) are complete for decisions RII has "
    "published; RII itself does not claim to hold every decision ever issued by these "
    "courts (courts publish selectively), so absence of a hit is not proof a decision "
    "does not exist."
)

RiiCourt = Literal["BVerfG", "BGH", "BAG", "BFH", "BVerwG", "BSG", "BPatG"]


class RiiCaseQuery(_Tolerant):
    """Arguments for the ``de_rii_case_search`` tool."""

    court: RiiCourt | None = Field(
        default=None, description="Filter by federal court, e.g. 'BVerfG'."
    )
    aktenzeichen_contains: str | None = Field(
        default=None, description="Substring match against the Aktenzeichen (docket number)."
    )
    date_from: str | None = Field(default=None, description="ISO or YYYYMMDD, inclusive.")
    date_to: str | None = Field(default=None, description="ISO or YYYYMMDD, inclusive.")
    limit: int = Field(default=20, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class RiiCaseInfo(_Tolerant):
    """Lightweight RII decision record - one TOC row."""

    court_raw: str
    court_type: str
    decision_date: str | None = None
    aktenzeichen: str | None = None
    doc_id: str
    zip_url: str
    modified: str | None = None

    human_readable_citation: str | None = None
    source_url: str | None = None


class RiiCaseSearchResult(_Tolerant):
    """Result of ``de_rii_case_search``."""

    total_items: int
    items: list[RiiCaseInfo] = Field(default_factory=list)
    query_echo: RiiCaseQuery | None = None
    note: str = RII_NOTE


class RiiCaseText(_Tolerant):
    """Result of ``de_rii_get_case_text``."""

    doc_id: str
    ecli: str | None = None
    eli_uri: str
    court: str | None = None
    spruchkoerper: str | None = None
    decision_date: str | None = None
    aktenzeichen: str | None = None
    doktyp: str | None = None
    norm: str | None = None
    human_readable_citation: str | None = None
    source_url: str
    titelzeile: str | None = None
    leitsatz: str | None = None
    tenor: str | None = None
    content: str | None = Field(default=None, description="Full text (Tatbestand + Gruende).")
    byte_size: int | None = None
    note: str = RII_NOTE


# --- Case law via Open Legal Data (de.openlegaldata.io) - feature 004 ---------

OLDP_NOTE = (
    "Source: Open Legal Data (de.openlegaldata.io), a community open-data aggregator "
    "of German case law across all court levels (federal AND state courts) - database "
    "under ODbL v1.0, decisions themselves gemeinfrei per § 5 UrhG. It is NOT an "
    "official government service and does not claim completeness; for the six federal "
    "supreme/constitutional courts prefer de_rii_case_search (official, complete). "
    "OLDP's unique value is the state-court layer (Oberlandesgerichte, Landgerichte, "
    "Amtsgerichte, state administrative/social/labor/finance courts)."
)


class OldpCaseQuery(_Tolerant):
    """Arguments for the ``de_oldp_case_search`` tool."""

    text: str | None = Field(
        default=None,
        description=(
            "Full-text search over decision content (Elasticsearch). When set, the "
            "metadata filters below are IGNORED (different upstream endpoint)."
        ),
    )
    court_slug: str | None = Field(
        default=None,
        description="Court slug, e.g. 'bverwg', 'ovgnrw', 'lg-nurnberg-furth'.",
    )
    file_number: str | None = Field(
        default=None, description="EXACT docket number match, e.g. '8 O 4860/25'."
    )
    date_after: str | None = Field(default=None, description="ISO date, inclusive lower bound.")
    date_before: str | None = Field(default=None, description="ISO date, inclusive upper bound.")
    page: int = Field(default=1, ge=1)


class OldpCaseInfo(_Tolerant):
    """Lightweight OLDP case record (normalised across both search shapes)."""

    id: int | None = None
    slug: str | None = None
    court_name: str | None = None
    court_slug: str | None = None
    court_jurisdiction: str | None = None
    court_level_of_appeal: str | None = None
    file_number: str | None = None
    date: str | None = None
    decision_type: str | None = None
    ecli: str | None = None
    snippets: list[str] | None = None

    eli_uri: str | None = None
    human_readable_citation: str | None = None
    source_url: str | None = None


class OldpCaseSearchResult(_Tolerant):
    """Result of ``de_oldp_case_search``."""

    total_items: int
    items: list[OldpCaseInfo] = Field(default_factory=list)
    query_echo: OldpCaseQuery | None = None
    note: str = OLDP_NOTE


class OldpCaseText(_Tolerant):
    """Result of ``de_oldp_get_case``."""

    id: int | None = None
    slug: str | None = None
    eli_uri: str
    ecli: str | None = None
    court_name: str | None = None
    file_number: str | None = None
    date: str | None = None
    decision_type: str | None = None
    human_readable_citation: str | None = None
    source_url: str
    content: str | None = Field(default=None, description="Full decision text (HTML).")
    byte_size: int | None = None
    note: str = OLDP_NOTE


# --- Parliamentary documents via Bundestag DIP - feature 004 ------------------

DIP_NOTE = (
    "Source: DIP (dip.bundestag.de), the German parliament's official documentation "
    "system, via its documented public API. Covers Bundestag and Bundesrat printed "
    "papers (Drucksachen), plenary transcripts and legislative procedures. DIP records "
    "legislative history - it does not carry consolidated statute text (use de_search "
    "for that)."
)

DipResource = Literal[
    "drucksache", "drucksache-text", "plenarprotokoll", "plenarprotokoll-text", "vorgang"
]


class DipSearchQuery(_Tolerant):
    """Arguments for the ``de_dip_search`` tool."""

    resource: DipResource = Field(
        default="drucksache",
        description=(
            "DIP resource type. Use 'drucksache' / 'plenarprotokoll' for metadata, "
            "the '-text' variants to include full text in results, 'vorgang' for "
            "legislative procedures."
        ),
    )
    titel: str | None = Field(default=None, description="Match against the title.")
    dokumentnummer: str | None = Field(
        default=None, description="Document number, e.g. '20/1' (exact)."
    )
    zuordnung: str | None = Field(default=None, description="'BT' (Bundestag) or 'BR' (Bundesrat).")
    wahlperiode: int | None = Field(default=None, description="Electoral term, e.g. 20.")
    vorgangstyp: str | None = Field(
        default=None, description="Procedure type (vorgang only), e.g. 'Gesetzgebung'."
    )
    date_start: str | None = Field(default=None, description="ISO date, inclusive.")
    date_end: str | None = Field(default=None, description="ISO date, inclusive.")
    cursor: str | None = Field(
        default=None,
        description="Opaque pagination cursor from the previous result; end is reached "
        "when the cursor stops changing.",
    )


class DipDocumentInfo(_Tolerant):
    """Lightweight DIP entity record."""

    id: str | None = None
    dokumentart: str | None = None
    drucksachetyp: str | None = None
    vorgangstyp: str | None = None
    dokumentnummer: str | None = None
    wahlperiode: int | None = None
    herausgeber: str | None = None
    titel: str | None = None
    datum: str | None = None
    text: str | None = None

    eli_uri: str | None = None
    human_readable_citation: str | None = None
    source_url: str | None = None


class DipSearchResult(_Tolerant):
    """Result of ``de_dip_search``."""

    total_items: int
    items: list[DipDocumentInfo] = Field(default_factory=list)
    cursor: str | None = None
    query_echo: DipSearchQuery | None = None
    note: str = DIP_NOTE


class DipDocumentText(_Tolerant):
    """Result of ``de_dip_get_document``."""

    id: str | None = None
    eli_uri: str
    dokumentart: str | None = None
    dokumentnummer: str | None = None
    wahlperiode: int | None = None
    herausgeber: str | None = None
    titel: str | None = None
    datum: str | None = None
    human_readable_citation: str | None = None
    source_url: str
    content: str | None = Field(default=None, description="Full document text (plain).")
    byte_size: int | None = None
    note: str = DIP_NOTE
