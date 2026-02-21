"""Thin wrappers around download statistics APIs for PyPI and npm."""

from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.schemas.package import DownloadStats


@dataclass
class PyPIStatsClient:
    """Client for pypistats.org download statistics."""

    base_url: str = "https://pypistats.org/api"
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
    async def fetch_recent(self, name: str) -> list[DownloadStats]:
        """Fetch recent download counts for a PyPI package."""
        client = await self._get_client()
        resp = await client.get(f"{self.base_url}/packages/{name}/recent")
        resp.raise_for_status()
        data: dict = resp.json()
        today: str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        stats_data: dict = data.get("data", {})
        results: list[DownloadStats] = []
        for period in ("last_day", "last_week", "last_month"):
            count = stats_data.get(period, 0)
            if count:
                results.append(
                    DownloadStats(period=period, date=today, download_count=count)
                )
        return results

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def fetch_overall(self, name: str) -> list[DownloadStats]:
        """Fetch overall download stats with daily breakdown."""
        client = await self._get_client()
        resp = await client.get(
            f"{self.base_url}/packages/{name}/overall",
            params={"mirrors": "true"},
        )
        resp.raise_for_status()
        data: dict = resp.json()
        results: list[DownloadStats] = []
        for entry in data.get("data", []):
            results.append(
                DownloadStats(
                    period="overall",
                    date=entry.get("date", ""),
                    download_count=entry.get("downloads", 0),
                )
            )
        return results


@dataclass
class NpmStatsClient:
    """Client for npm download statistics API."""

    base_url: str = "https://api.npmjs.org/downloads"
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
    async def fetch_point(self, name: str, period: str = "last-month") -> list[DownloadStats]:
        """Fetch aggregate download count for a period."""
        client = await self._get_client()
        resp = await client.get(f"{self.base_url}/point/{period}/{name}")
        resp.raise_for_status()
        data: dict = resp.json()
        return [
            DownloadStats(
                period=period,
                date=data.get("end", ""),
                download_count=data.get("downloads", 0),
            )
        ]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def fetch_range(self, name: str, period: str = "last-month") -> list[DownloadStats]:
        """Fetch daily download counts for a period."""
        client = await self._get_client()
        resp = await client.get(f"{self.base_url}/range/{period}/{name}")
        resp.raise_for_status()
        data: dict = resp.json()
        results: list[DownloadStats] = []
        for entry in data.get("downloads", []):
            results.append(
                DownloadStats(
                    period=period,
                    date=entry.get("day", ""),
                    download_count=entry.get("downloads", 0),
                )
            )
        return results
