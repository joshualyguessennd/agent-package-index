"""Orchestrator task that chains the full crawl pipeline."""

import logging

from celery import chain, shared_task

from app.schemas.tasks import FullCrawlResult
from app.tasks.compute_scores import recompute_all_scores
from app.tasks.crawl_npm import crawl_npm_package_list
from app.tasks.crawl_pypi import crawl_pypi_package_list
from app.tasks.crawl_vulnerabilities import crawl_vulnerabilities_batch

logger = logging.getLogger(__name__)


@shared_task(name="run_full_crawl")
def run_full_crawl() -> FullCrawlResult:
    """Run the full crawl pipeline: list -> detail -> vuln -> score."""
    pipeline = chain(
        crawl_pypi_package_list.si(),
        crawl_npm_package_list.si(),
        crawl_vulnerabilities_batch.si(),
        recompute_all_scores.si(),
    )
    pipeline.apply_async()
    logger.info("Full crawl pipeline dispatched")
    return FullCrawlResult(status="dispatched")
