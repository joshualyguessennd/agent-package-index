"""HTTP client for the PyPI registry API."""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.schemas.package import (
    DownloadStats,
    MaintainerInfo,
    PackageMetadata,
    VersionInfo,
)


@dataclass
class PyPIListResponse:
    """Response from PyPI simple index listing."""

    package_names: list[str] = field(default_factory=list)
    last_serial: str | None = None


@dataclass
class PyPIClient:
    """Client for PyPI JSON and Simple Index APIs."""

    base_url: str = "https://pypi.org"
    stats_url: str = "https://pypistats.org/api"
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
    async def fetch_package_list(self) -> PyPIListResponse:
        """Fetch the full package name list from PyPI simple index."""
        client = await self._get_client()
        resp = await client.get(
            f"{self.base_url}/simple/",
            headers={"Accept": "application/vnd.pypi.simple.v1+json"},
        )
        resp.raise_for_status()
        data: dict = resp.json()
        names: list[str] = [p["name"] for p in data.get("projects", [])]
        serial: str | None = resp.headers.get("X-PyPI-Last-Serial")
        return PyPIListResponse(package_names=names, last_serial=serial)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def fetch_package_detail(self, name: str) -> PackageMetadata:
        """Fetch detailed package metadata from PyPI JSON API."""
        client = await self._get_client()
        resp = await client.get(f"{self.base_url}/pypi/{name}/json")
        resp.raise_for_status()
        data: dict = resp.json()
        return self._parse_package_detail(data)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def fetch_versions(self, name: str) -> list[VersionInfo]:
        """Fetch all versions for a package."""
        client = await self._get_client()
        resp = await client.get(f"{self.base_url}/pypi/{name}/json")
        resp.raise_for_status()
        data: dict = resp.json()
        return self._parse_versions(data)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def fetch_downloads(self, name: str) -> list[DownloadStats]:
        """Fetch recent download stats from pypistats.org."""
        client = await self._get_client()
        resp = await client.get(f"{self.stats_url}/packages/{name}/recent")
        resp.raise_for_status()
        data: dict = resp.json()
        return self._parse_downloads(data)

    def _parse_package_detail(self, data: dict) -> PackageMetadata:
        """Parse PyPI JSON API response into PackageMetadata."""
        info: dict = data.get("info", {})
        releases: dict = data.get("releases", {})

        release_dates: list[datetime] = []
        for version_files in releases.values():
            for file_info in version_files:
                upload_time = file_info.get("upload_time_iso_8601")
                if upload_time:
                    try:
                        release_dates.append(
                            datetime.fromisoformat(upload_time.replace("Z", "+00:00"))
                        )
                    except ValueError:
                        pass

        first_release: datetime | None = min(release_dates) if release_dates else None
        latest_release: datetime | None = max(release_dates) if release_dates else None

        maintainers: list[MaintainerInfo] = []
        if info.get("maintainer"):
            maintainers.append(
                MaintainerInfo(
                    name=info["maintainer"],
                    email=info.get("maintainer_email"),
                )
            )

        keywords_raw: str = info.get("keywords") or ""
        keywords: list[str] = [
            k.strip() for k in keywords_raw.replace(",", " ").split() if k.strip()
        ]

        project_urls: dict = info.get("project_urls") or {}

        return PackageMetadata(
            registry="pypi",
            name=info.get("name", ""),
            normalized_name=self._normalize_name(info.get("name", "")),
            summary=info.get("summary"),
            description=info.get("description"),
            homepage_url=info.get("home_page") or project_urls.get("Homepage"),
            repository_url=project_urls.get("Repository") or project_urls.get("Source"),
            documentation_url=project_urls.get("Documentation"),
            license=info.get("license"),
            keywords=keywords,
            classifiers=info.get("classifiers", []),
            requires_python=info.get("requires_python"),
            author=info.get("author"),
            author_email=info.get("author_email"),
            maintainers=maintainers,
            first_release_at=first_release,
            latest_release_at=latest_release,
            is_yanked=False,
        )

    def _parse_versions(self, data: dict) -> list[VersionInfo]:
        """Parse PyPI JSON API response into list of VersionInfo."""
        releases: dict = data.get("releases", {})
        info: dict = data.get("info", {})
        latest_ver: str = info.get("version", "")
        versions: list[VersionInfo] = []

        for ver_str, files in releases.items():
            if not files:
                continue
            release_date: datetime | None = None
            total_size: int = 0
            for f in files:
                upload_time = f.get("upload_time_iso_8601")
                if upload_time and release_date is None:
                    try:
                        release_date = datetime.fromisoformat(
                            upload_time.replace("Z", "+00:00")
                        )
                    except ValueError:
                        pass
                total_size += f.get("size", 0)

            requires: list[str] = info.get("requires_dist") or []
            versions.append(
                VersionInfo(
                    version=ver_str,
                    release_date=release_date,
                    dependencies=requires if ver_str == latest_ver else [],
                    dep_count=len(requires) if ver_str == latest_ver else 0,
                    size_bytes=total_size if total_size > 0 else None,
                    is_yanked=any(f.get("yanked", False) for f in files),
                    is_latest=ver_str == latest_ver,
                )
            )
        return versions

    def _parse_downloads(self, data: dict) -> list[DownloadStats]:
        """Parse pypistats recent downloads response."""
        stats_data: dict = data.get("data", {})
        today: str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        results: list[DownloadStats] = []
        for period in ("last_day", "last_week", "last_month"):
            count = stats_data.get(period, 0)
            if count:
                results.append(
                    DownloadStats(period=period, date=today, download_count=count)
                )
        return results

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Normalize a PyPI package name per PEP 503."""
        return re.sub(r"[-_.]+", "-", name).lower()
