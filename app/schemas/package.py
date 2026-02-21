"""Schemas for package data used across crawlers, API, and scoring."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


@dataclass
class MaintainerInfo:
    """A package maintainer."""

    name: str
    email: str | None = None


@dataclass
class PackageMetadata:
    """Core metadata for a package from any registry."""

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
    maintainers: list[MaintainerInfo] = field(default_factory=list)
    first_release_at: datetime | None = None
    latest_release_at: datetime | None = None
    is_deprecated: bool = False
    is_yanked: bool = False


@dataclass
class VersionInfo:
    """A single version of a package."""

    version: str
    release_date: datetime | None = None
    dependencies: list[str] = field(default_factory=list)
    dep_count: int = 0
    size_bytes: int | None = None
    is_yanked: bool = False
    is_latest: bool = False


@dataclass
class DownloadStats:
    """Download statistics for a package over a period."""

    period: str
    date: str
    download_count: int = 0


class Severity(Enum):
    """Vulnerability severity levels."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class VulnerabilityInfo:
    """A known vulnerability for a package."""

    cve_id: str | None = None
    advisory_id: str | None = None
    severity: Severity | None = None
    summary: str | None = None
    affected_versions: str | None = None
    fixed_version: str | None = None
    published_at: datetime | None = None
    source: str | None = None
    source_url: str | None = None
