"""Schemas for Celery task return values."""

from dataclasses import dataclass


@dataclass
class CrawlListResult:
    """Result from a package list crawl task."""

    processed: int
    cursor: str | None = None


@dataclass
class CrawlDetailResult:
    """Result from a single package detail crawl task."""

    package: str
    status: str


@dataclass
class CrawlBatchResult:
    """Result from a batch crawl task (downloads, etc.)."""

    processed: int


@dataclass
class VulnerabilityCrawlResult:
    """Result from a vulnerability crawl task."""

    processed: int
    vulnerabilities: int


@dataclass
class ScoreComputeResult:
    """Result from computing a single package's reputation score."""

    package_id: int
    overall_score: float


@dataclass
class ScoreComputeError:
    """Error result when score computation fails to find the package."""

    error: str


@dataclass
class RecomputeAllResult:
    """Result from queuing recomputation of all scores."""

    queued: int


@dataclass
class FullCrawlResult:
    """Result from dispatching the full crawl pipeline."""

    status: str


@dataclass
class BatchLookupResult:
    """A single result from a batch package lookup."""

    registry: str
    name: str
    found: bool
    summary: str | None = None
    overall_score: float | None = None
