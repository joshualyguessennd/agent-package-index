"""HTTP client for the OSV (Open Source Vulnerabilities) API."""

from dataclasses import dataclass, field
from datetime import datetime

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.schemas.package import Severity, VulnerabilityInfo


@dataclass
class OSVClient:
    """Client for the OSV.dev vulnerability database API."""

    base_url: str = "https://api.osv.dev/v1"
    timeout: float = 30.0
    _client: httpx.AsyncClient | None = field(default=None, repr=False)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers={"Content-Type": "application/json"},
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def query_vulnerabilities(
        self, name: str, ecosystem: str
    ) -> list[VulnerabilityInfo]:
        """Query OSV for vulnerabilities affecting a package.

        Args:
            name: Package name (e.g., 'requests').
            ecosystem: OSV ecosystem identifier (e.g., 'PyPI', 'npm').

        Returns:
            List of parsed vulnerability records.
        """
        client = await self._get_client()
        resp = await client.post(
            f"{self.base_url}/query",
            json={"package": {"name": name, "ecosystem": ecosystem}},
        )
        resp.raise_for_status()
        data: dict = resp.json()
        return self._parse_vulnerabilities(data)

    def _parse_vulnerabilities(self, data: dict) -> list[VulnerabilityInfo]:
        """Parse OSV query response into VulnerabilityInfo list."""
        vulns: list[VulnerabilityInfo] = []
        for vuln in data.get("vulns", []):
            severity = self._extract_severity(vuln)
            affected_versions = self._extract_affected_versions(vuln)
            fixed_version = self._extract_fixed_version(vuln)

            aliases: list[str] = vuln.get("aliases", [])
            cve_id: str | None = next((a for a in aliases if a.startswith("CVE-")), None)

            published_str: str | None = vuln.get("published")
            published_at: datetime | None = None
            if published_str:
                try:
                    published_at = datetime.fromisoformat(
                        published_str.replace("Z", "+00:00")
                    )
                except ValueError:
                    pass

            references: list[dict] = vuln.get("references", [])
            source_url: str | None = (
                references[0].get("url") if references else None
            )

            vulns.append(
                VulnerabilityInfo(
                    cve_id=cve_id,
                    advisory_id=vuln.get("id"),
                    severity=severity,
                    summary=vuln.get("summary") or vuln.get("details", "")[:500],
                    affected_versions=affected_versions,
                    fixed_version=fixed_version,
                    published_at=published_at,
                    source="osv",
                    source_url=source_url,
                )
            )
        return vulns

    @staticmethod
    def _extract_severity(vuln: dict) -> Severity | None:
        """Extract the highest severity from a vulnerability record."""
        severity_list: list[dict] = vuln.get("severity", [])
        if not severity_list:
            db_specific: dict = vuln.get("database_specific", {})
            raw: str | None = db_specific.get("severity")
            if raw:
                try:
                    return Severity(raw.upper())
                except ValueError:
                    return None
            return None

        scores: list[str] = []
        for s in severity_list:
            score_str: str = s.get("score", "")
            if score_str:
                scores.append(score_str)

        if not scores:
            return None

        # Map CVSS scores to severity levels
        try:
            max_score: float = max(float(s) for s in scores)
            if max_score >= 9.0:
                return Severity.CRITICAL
            if max_score >= 7.0:
                return Severity.HIGH
            if max_score >= 4.0:
                return Severity.MEDIUM
            return Severity.LOW
        except ValueError:
            return None

    @staticmethod
    def _extract_affected_versions(vuln: dict) -> str | None:
        """Extract affected version ranges from a vulnerability."""
        affected: list[dict] = vuln.get("affected", [])
        ranges_strs: list[str] = []
        for entry in affected:
            for r in entry.get("ranges", []):
                events: list[dict] = r.get("events", [])
                introduced: str | None = None
                fixed: str | None = None
                for event in events:
                    if "introduced" in event:
                        introduced = event["introduced"]
                    if "fixed" in event:
                        fixed = event["fixed"]
                if introduced:
                    range_str = f">={introduced}"
                    if fixed:
                        range_str += f", <{fixed}"
                    ranges_strs.append(range_str)
        return "; ".join(ranges_strs) if ranges_strs else None

    @staticmethod
    def _extract_fixed_version(vuln: dict) -> str | None:
        """Extract the first fixed version from a vulnerability."""
        affected: list[dict] = vuln.get("affected", [])
        for entry in affected:
            for r in entry.get("ranges", []):
                for event in r.get("events", []):
                    if "fixed" in event:
                        return event["fixed"]
        return None
