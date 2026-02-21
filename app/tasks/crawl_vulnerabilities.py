"""Celery tasks for crawling vulnerability data via OSV."""

import asyncio
import logging

from celery import shared_task
from sqlalchemy import select

from app.models import Package, SeverityType, Vulnerability
from app.schemas.tasks import VulnerabilityCrawlResult
from app.services.crawlers.osv_client import OSVClient
from app.tasks._db import get_task_session, remove_task_session

logger = logging.getLogger(__name__)

REGISTRY_TO_ECOSYSTEM: dict[str, str] = {
    "pypi": "PyPI",
    "npm": "npm",
}


def _run_async(coro: object) -> object:
    """Run an async coroutine in a new event loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@shared_task(name="crawl_vulnerabilities_batch")
def crawl_vulnerabilities_batch(
    package_ids: list[int] | None = None, limit: int = 100
) -> VulnerabilityCrawlResult:
    """Query OSV for vulnerabilities affecting packages.

    If package_ids is None, picks the oldest-crawled packages up to limit.
    """
    db = get_task_session()
    processed: int = 0
    vuln_count: int = 0
    try:
        if package_ids is None:
            packages = db.execute(
                select(Package)
                .order_by(Package.crawled_at.asc().nulls_first())
                .limit(limit)
            ).scalars().all()
        else:
            packages = db.execute(
                select(Package).where(Package.id.in_(package_ids))
            ).scalars().all()

        client = OSVClient()

        for pkg in packages:
            ecosystem: str | None = REGISTRY_TO_ECOSYSTEM.get(str(pkg.registry.value))
            if not ecosystem:
                continue

            try:
                vulns = _run_async(
                    client.query_vulnerabilities(pkg.name, ecosystem)
                )

                # Clear old vulnerabilities for this package
                old_vulns = db.execute(
                    select(Vulnerability).where(
                        Vulnerability.package_id == pkg.id
                    )
                ).scalars().all()
                for old in old_vulns:
                    db.delete(old)

                for v in vulns:
                    orm_severity = (
                        SeverityType(v.severity.value) if v.severity else None
                    )
                    db.add(Vulnerability(
                        package_id=pkg.id,
                        cve_id=v.cve_id,
                        advisory_id=v.advisory_id,
                        severity=orm_severity,
                        summary=v.summary,
                        affected_versions=v.affected_versions,
                        fixed_version=v.fixed_version,
                        published_at=v.published_at,
                        source=v.source,
                        source_url=v.source_url,
                    ))
                    vuln_count += 1

                processed += 1
            except Exception:
                logger.warning("Failed to fetch vulns for %s/%s", pkg.registry, pkg.name)

        _run_async(client.close())
        db.commit()
        logger.info("Vulnerability crawl: %d packages, %d vulns", processed, vuln_count)
        return VulnerabilityCrawlResult(processed=processed, vulnerabilities=vuln_count)
    except Exception as e:
        db.rollback()
        raise e
    finally:
        remove_task_session()
