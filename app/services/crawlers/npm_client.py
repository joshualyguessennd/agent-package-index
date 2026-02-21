"""HTTP client for the npm registry API."""

from dataclasses import dataclass, field
from datetime import datetime

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.schemas.package import (
    DownloadStats,
    MaintainerInfo,
    PackageMetadata,
    VersionInfo,
)


@dataclass
class NpmChangesResponse:
    """Response from npm CouchDB _changes feed."""

    package_names: list[str] = field(default_factory=list)
    last_seq: str | None = None


@dataclass
class NpmClient:
    """Client for npm registry and downloads APIs."""

    registry_url: str = "https://registry.npmjs.org"
    downloads_url: str = "https://api.npmjs.org/downloads"
    replicate_url: str = "https://replicate.npmjs.com"
    timeout: float = 30.0
    _client: httpx.AsyncClient | None = field(default=None, repr=False)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers={"Accept": "application/json"},
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def fetch_changes(self, since_seq: str = "0") -> NpmChangesResponse:
        """Fetch recent package changes from CouchDB _changes feed."""
        client = await self._get_client()
        resp = await client.get(
            f"{self.replicate_url}/_changes",
            params={"since": since_seq, "limit": "1000"},
        )
        resp.raise_for_status()
        data: dict = resp.json()
        names: list[str] = [
            r["id"]
            for r in data.get("results", [])
            if not r.get("id", "").startswith("_design/")
        ]
        last_seq: str | None = str(data.get("last_seq"))
        return NpmChangesResponse(package_names=names, last_seq=last_seq)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def fetch_package_detail(self, name: str) -> PackageMetadata:
        """Fetch detailed package metadata from npm registry."""
        client = await self._get_client()
        resp = await client.get(f"{self.registry_url}/{name}")
        resp.raise_for_status()
        data: dict = resp.json()
        return self._parse_package_detail(data)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def fetch_versions(self, name: str) -> list[VersionInfo]:
        """Fetch all versions for a package."""
        client = await self._get_client()
        resp = await client.get(f"{self.registry_url}/{name}")
        resp.raise_for_status()
        data: dict = resp.json()
        return self._parse_versions(data)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def fetch_downloads(self, name: str, period: str = "last-month") -> list[DownloadStats]:
        """Fetch download counts from npm downloads API."""
        client = await self._get_client()
        resp = await client.get(f"{self.downloads_url}/point/{period}/{name}")
        resp.raise_for_status()
        data: dict = resp.json()
        return self._parse_downloads(data, period)

    def _parse_package_detail(self, data: dict) -> PackageMetadata:
        """Parse npm registry response into PackageMetadata."""
        latest_tag: str = data.get("dist-tags", {}).get("latest", "")
        latest_info: dict = data.get("versions", {}).get(latest_tag, {})
        time_info: dict = data.get("time", {})

        first_release: datetime | None = None
        latest_release: datetime | None = None
        if time_info.get("created"):
            first_release = _parse_iso(time_info["created"])
        if time_info.get("modified"):
            latest_release = _parse_iso(time_info["modified"])

        maintainers: list[MaintainerInfo] = [
            MaintainerInfo(name=m.get("name", ""), email=m.get("email"))
            for m in data.get("maintainers", [])
        ]

        keywords: list[str] = data.get("keywords") or latest_info.get("keywords") or []
        repo_info: dict = data.get("repository") or {}
        repo_url: str | None = repo_info.get("url") if isinstance(repo_info, dict) else None

        return PackageMetadata(
            registry="npm",
            name=data.get("name", ""),
            normalized_name=data.get("name", "").lower(),
            summary=data.get("description") or latest_info.get("description"),
            description=data.get("readme"),
            homepage_url=data.get("homepage") or latest_info.get("homepage"),
            repository_url=repo_url,
            documentation_url=None,
            license=latest_info.get("license") or data.get("license"),
            keywords=keywords,
            classifiers=[],
            requires_python=None,
            author=_extract_author_name(data.get("author")),
            author_email=_extract_author_email(data.get("author")),
            maintainers=maintainers,
            first_release_at=first_release,
            latest_release_at=latest_release,
            is_deprecated=bool(data.get("deprecated")),
        )

    def _parse_versions(self, data: dict) -> list[VersionInfo]:
        """Parse npm registry response into list of VersionInfo."""
        versions_dict: dict = data.get("versions", {})
        time_info: dict = data.get("time", {})
        latest_tag: str = data.get("dist-tags", {}).get("latest", "")
        versions: list[VersionInfo] = []

        for ver_str, ver_data in versions_dict.items():
            release_date: datetime | None = None
            if ver_str in time_info:
                release_date = _parse_iso(time_info[ver_str])

            deps: dict = ver_data.get("dependencies", {})
            dep_list: list[str] = [f"{k}@{v}" for k, v in deps.items()]
            dist: dict = ver_data.get("dist", {})

            versions.append(
                VersionInfo(
                    version=ver_str,
                    release_date=release_date,
                    dependencies=dep_list,
                    dep_count=len(dep_list),
                    size_bytes=dist.get("unpackedSize"),
                    is_yanked=bool(ver_data.get("deprecated")),
                    is_latest=ver_str == latest_tag,
                )
            )
        return versions

    def _parse_downloads(self, data: dict, period: str) -> list[DownloadStats]:
        """Parse npm downloads API response."""
        count: int = data.get("downloads", 0)
        date_str: str = data.get("end", "")
        return [DownloadStats(period=period, date=date_str, download_count=count)]


def _parse_iso(value: str) -> datetime | None:
    """Parse an ISO 8601 date string, returning None on failure."""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _extract_author_name(author: str | dict | None) -> str | None:
    """Extract author name from npm author field (string or object)."""
    if isinstance(author, dict):
        return author.get("name")
    if isinstance(author, str):
        return author
    return None


def _extract_author_email(author: str | dict | None) -> str | None:
    """Extract author email from npm author field."""
    if isinstance(author, dict):
        return author.get("email")
    return None
