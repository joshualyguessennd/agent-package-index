"""Celery tasks for crawling PyPI packages."""

import asyncio
import logging
from dataclasses import asdict
from datetime import datetime, timezone

from celery import shared_task
from sqlalchemy import select

from app.models import CrawlState, DownloadStat, Package, PackageVersion
from app.schemas.tasks import CrawlBatchResult, CrawlDetailResult, CrawlListResult
from app.services.crawlers.pypi_client import PyPIClient
from app.tasks._db import get_task_session, remove_task_session

logger = logging.getLogger(__name__)


def _run_async(coro: object) -> object:
    """Run an async coroutine in a new event loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


async def _fetch_pypi_list(client: PyPIClient) -> object:
    """Fetch package list and close the client in the same event loop."""
    try:
        return await client.fetch_package_list()
    finally:
        await client.close()


async def _fetch_pypi_detail(client: PyPIClient, name: str) -> tuple:
    """Fetch package detail + versions and close the client in the same loop."""
    try:
        metadata = await client.fetch_package_detail(name)
        versions = await client.fetch_versions(name)
        return metadata, versions
    finally:
        await client.close()


async def _fetch_pypi_downloads_batch(
    client: PyPIClient, names: list[str]
) -> list[tuple[str, list]]:
    """Fetch downloads for a batch of packages, then close client."""
    results: list[tuple[str, list]] = []
    try:
        for name in names:
            try:
                stats = await client.fetch_downloads(name)
                results.append((name, stats))
            except Exception:
                logger.warning("Failed to fetch downloads for %s", name)
    finally:
        await client.close()
    return results


@shared_task(name="crawl_pypi_package_list")
def crawl_pypi_package_list() -> dict:
    """Crawl the PyPI simple index for package names."""
    db = get_task_session()
    try:
        client = PyPIClient()
        result = _run_async(_fetch_pypi_list(client))

        new_count: int = 0
        for name in result.package_names:
            normalized: str = PyPIClient._normalize_name(name)
            existing = db.execute(
                select(Package).where(
                    Package.registry == "pypi",
                    Package.normalized_name == normalized,
                )
            ).scalar_one_or_none()
            if existing is None:
                db.add(Package(
                    registry="pypi",
                    name=name,
                    normalized_name=normalized,
                ))
            new_count += 1

        # Update crawl_state
        if result.last_serial:
            state = db.execute(
                select(CrawlState).where(
                    CrawlState.registry == "pypi",
                    CrawlState.task_type == "package_list",
                )
            ).scalar_one_or_none()
            if state is None:
                db.add(CrawlState(
                    registry="pypi",
                    task_type="package_list",
                    cursor=result.last_serial,
                    status="completed",
                    last_run_at=datetime.now(tz=timezone.utc),
                ))
            else:
                state.cursor = result.last_serial
                state.status = "completed"
                state.last_run_at = datetime.now(tz=timezone.utc)

        db.commit()
        logger.info("PyPI package list crawl: %d packages processed", new_count)
        return asdict(CrawlListResult(processed=new_count, cursor=result.last_serial))
    except Exception as e:
        db.rollback()
        logger.exception("PyPI package list crawl failed")
        raise e
    finally:
        remove_task_session()


@shared_task(name="crawl_pypi_package_detail")
def crawl_pypi_package_detail(package_name: str) -> dict:
    """Crawl detail for a single PyPI package and upsert into the database."""
    db = get_task_session()
    try:
        client = PyPIClient()
        metadata, versions = _run_async(_fetch_pypi_detail(client, package_name))

        maintainers_json: list[dict[str, str | None]] = [
            {"name": m.name, "email": m.email} for m in metadata.maintainers
        ]

        pkg = db.execute(
            select(Package).where(
                Package.registry == "pypi",
                Package.normalized_name == metadata.normalized_name,
            )
        ).scalar_one_or_none()

        now = datetime.now(tz=timezone.utc)

        if pkg is None:
            pkg = Package(registry="pypi", name=metadata.name,
                          normalized_name=metadata.normalized_name)
            db.add(pkg)

        pkg.summary = metadata.summary
        pkg.description = metadata.description
        pkg.homepage_url = metadata.homepage_url
        pkg.repository_url = metadata.repository_url
        pkg.documentation_url = metadata.documentation_url
        pkg.license = metadata.license
        pkg.keywords = metadata.keywords
        pkg.classifiers = metadata.classifiers
        pkg.requires_python = metadata.requires_python
        pkg.author = metadata.author
        pkg.author_email = metadata.author_email
        pkg.maintainers = maintainers_json
        pkg.first_release_at = metadata.first_release_at
        pkg.latest_release_at = metadata.latest_release_at
        pkg.crawled_at = now

        db.flush()

        for v in versions:
            existing_ver = db.execute(
                select(PackageVersion).where(
                    PackageVersion.package_id == pkg.id,
                    PackageVersion.version == v.version,
                )
            ).scalar_one_or_none()
            if existing_ver is None:
                db.add(PackageVersion(
                    package_id=pkg.id,
                    version=v.version,
                    release_date=v.release_date,
                    dependencies=v.dependencies,
                    dep_count=v.dep_count,
                    size_bytes=v.size_bytes,
                    is_yanked=v.is_yanked,
                    is_latest=v.is_latest,
                ))

        db.commit()
        logger.info("PyPI detail crawl: %s", package_name)
        return asdict(CrawlDetailResult(package=package_name, status="ok"))
    except Exception as e:
        db.rollback()
        logger.exception("PyPI detail crawl failed for %s", package_name)
        raise e
    finally:
        remove_task_session()


@shared_task(name="crawl_pypi_downloads_batch")
def crawl_pypi_downloads_batch(package_names: list[str]) -> dict:
    """Crawl download stats for a batch of PyPI packages."""
    db = get_task_session()
    processed: int = 0
    try:
        client = PyPIClient()
        fetched = _run_async(_fetch_pypi_downloads_batch(client, package_names))

        for name, stats in fetched:
            normalized: str = PyPIClient._normalize_name(name)
            pkg = db.execute(
                select(Package).where(
                    Package.registry == "pypi",
                    Package.normalized_name == normalized,
                )
            ).scalar_one_or_none()
            if pkg:
                for s in stats:
                    existing = db.execute(
                        select(DownloadStat).where(
                            DownloadStat.package_id == pkg.id,
                            DownloadStat.period == s.period,
                            DownloadStat.date == s.date,
                        )
                    ).scalar_one_or_none()
                    if existing is None:
                        db.add(DownloadStat(
                            package_id=pkg.id,
                            period=s.period,
                            date=s.date,
                            download_count=s.download_count,
                        ))
                    else:
                        existing.download_count = s.download_count
            processed += 1

        db.commit()
        return asdict(CrawlBatchResult(processed=processed))
    except Exception as e:
        db.rollback()
        raise e
    finally:
        remove_task_session()
