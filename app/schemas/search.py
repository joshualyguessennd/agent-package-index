"""Schemas for search queries and results."""

from dataclasses import dataclass, field

from app.schemas.package import Severity


@dataclass
class SearchParams:
    """Parameters for a package search query."""

    q: str
    registry: str | None = None
    min_score: float = 0.0
    limit: int = 20
    offset: int = 0


@dataclass
class SearchResultItem:
    """A single item in search results."""

    id: int
    registry: str
    name: str
    summary: str | None = None
    overall_score: float = 0.0
    maintenance: float = 0.0
    vulnerability: float = 0.0
    dependency: float = 0.0
    popularity: float = 0.0
    maintainer_score: float = 0.0
    license_score: float = 0.0
    rank: float = 0.0


@dataclass
class SearchResponse:
    """Full response for a search query."""

    items: list[SearchResultItem] = field(default_factory=list)
    total: int = 0
    limit: int = 20
    offset: int = 0


@dataclass
class PackageDetailResponse:
    """Full detail response for a single package."""

    id: int
    registry: str
    name: str
    normalized_name: str
    summary: str | None = None
    description: str | None = None
    homepage_url: str | None = None
    repository_url: str | None = None
    documentation_url: str | None = None
    license: str | None = None
    keywords: list[str] = field(default_factory=list)
    classifiers: list[str] = field(default_factory=list)
    requires_python: str | None = None
    author: str | None = None
    author_email: str | None = None
    latest_version: str | None = None
    latest_release_at: str | None = None
    is_deprecated: bool = False
    reputation: "ReputationBreakdown | None" = None
    vulnerabilities: list["VulnerabilityItem"] = field(default_factory=list)
    download_stats: list["DownloadStatItem"] = field(default_factory=list)


@dataclass
class ReputationBreakdown:
    """Reputation score breakdown for API responses."""

    overall_score: float = 0.0
    maintenance: float = 0.0
    vulnerability: float = 0.0
    dependency: float = 0.0
    popularity: float = 0.0
    maintainer: float = 0.0
    license: float = 0.0
    computed_at: str | None = None


@dataclass
class VulnerabilityItem:
    """Vulnerability info for API responses."""

    cve_id: str | None = None
    advisory_id: str | None = None
    severity: Severity | None = None
    summary: str | None = None
    affected_versions: str | None = None
    fixed_version: str | None = None
    source: str | None = None


@dataclass
class DownloadStatItem:
    """Download stat for API responses."""

    period: str
    date: str
    download_count: int = 0


@dataclass
class IndexStats:
    """Overview statistics for the package index."""

    total_packages: int = 0
    by_registry: dict[str, int] = field(default_factory=dict)
    score_distribution: dict[str, int] = field(default_factory=dict)
    last_crawl_at: str | None = None


@dataclass
class BatchLookupItem:
    """A single item in a batch lookup request."""

    registry: str
    name: str


@dataclass
class VersionListItem:
    """A version entry for version listing endpoint."""

    version: str
    release_date: str | None = None
    dep_count: int = 0
    size_bytes: int | None = None
    is_yanked: bool = False
    is_latest: bool = False
