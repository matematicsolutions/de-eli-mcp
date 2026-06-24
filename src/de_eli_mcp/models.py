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
