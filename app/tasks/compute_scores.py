"""Celery tasks for computing reputation scores."""

import logging
from dataclasses import asdict
from datetime import datetime, timezone

from celery import shared_task
from sqlalchemy import func, select

from app.models import (
    DownloadStat,
    Package,
    PackageVersion,
    ReputationScore,
    SeverityType,
    Vulnerability,
)
from app.schemas.scoring import (
    DependencyInput,
    LicenseInput,
    MaintainerInput,
    MaintenanceInput,
    PopularityInput,
    ScoringInput,
    VulnerabilityInput,
)
from app.schemas.tasks import RecomputeAllResult, ScoreComputeError, ScoreComputeResult
from app.services.scoring import compute_reputation
from app.tasks._db import get_task_session, remove_task_session

logger = logging.getLogger(__name__)


@shared_task(name="compute_reputation_score")
def compute_reputation_score(
    package_id: int,
) -> ScoreComputeResult | ScoreComputeError:
    """Compute and store the reputation score for a single package."""
    db = get_task_session()
    try:
        pkg = db.execute(
            select(Package).where(Package.id == package_id)
        ).scalar_one_or_none()

        if not pkg:
            return asdict(ScoreComputeError(error="package not found"))

        # Count releases and get latest version
        release_count: int = db.execute(
            select(func.count()).select_from(PackageVersion).where(
                PackageVersion.package_id == package_id
            )
        ).scalar_one()

        latest_ver_row = db.execute(
            select(PackageVersion.version).where(
                PackageVersion.package_id == package_id,
                PackageVersion.is_latest.is_(True),
            )
        ).first()
        latest_version: str | None = latest_ver_row[0] if latest_ver_row else None

        # Count vulnerabilities by severity
        vulns = db.execute(
            select(Vulnerability).where(
                Vulnerability.package_id == package_id
            )
        ).scalars().all()

        vuln_input = VulnerabilityInput()
        for v in vulns:
            vuln_input.total_count += 1
            if v.fixed_version is None:
                vuln_input.unpatched_count += 1
            if v.severity == SeverityType.CRITICAL:
                vuln_input.critical_count += 1
            elif v.severity == SeverityType.HIGH:
                vuln_input.high_count += 1
            elif v.severity == SeverityType.MEDIUM:
                vuln_input.medium_count += 1
            else:
                vuln_input.low_count += 1

        # Dep count from latest version
        dep_row = db.execute(
            select(PackageVersion.dep_count).where(
                PackageVersion.package_id == package_id,
                PackageVersion.is_latest.is_(True),
            )
        ).first()
        dep_count: int = dep_row[0] if dep_row else 0

        # Monthly downloads
        dl_row = db.execute(
            select(DownloadStat.download_count)
            .where(
                DownloadStat.package_id == package_id,
                DownloadStat.period == "last_month",
            )
            .order_by(DownloadStat.date.desc())
            .limit(1)
        ).first()
        monthly_downloads: int = dl_row[0] if dl_row else 0

        scoring_input = ScoringInput(
            maintenance=MaintenanceInput(
                latest_release_at=pkg.latest_release_at,
                first_release_at=pkg.first_release_at,
                release_count=release_count,
                latest_version=latest_version,
            ),
            vulnerability=vuln_input,
            dependency=DependencyInput(direct_dep_count=dep_count),
            popularity=PopularityInput(monthly_downloads=monthly_downloads),
            maintainer=MaintainerInput(),
            license=LicenseInput(license_name=pkg.license),
        )

        result = compute_reputation(scoring_input)

        # Upsert reputation score
        details = {
            d.name: {"score": d.score, "details": d.details}
            for d in result.dimensions
        }

        rep = db.execute(
            select(ReputationScore).where(
                ReputationScore.package_id == package_id
            )
        ).scalar_one_or_none()

        now = datetime.now(tz=timezone.utc)
        if rep is None:
            rep = ReputationScore(package_id=package_id)
            db.add(rep)

        rep.maintenance = result.maintenance
        rep.vulnerability = result.vulnerability
        rep.dependency = result.dependency
        rep.popularity = result.popularity
        rep.maintainer = result.maintainer
        rep.license = result.license
        rep.overall_score = result.overall_score
        rep.score_details = details
        rep.computed_at = now

        db.commit()
        logger.info(
            "Computed reputation for package %d: %.4f",
            package_id, result.overall_score,
        )
        return asdict(ScoreComputeResult(
            package_id=package_id, overall_score=result.overall_score
        ))
    except Exception as e:
        db.rollback()
        logger.exception("Failed to compute score for package %d", package_id)
        raise e
    finally:
        remove_task_session()


@shared_task(name="recompute_all_scores")
def recompute_all_scores(batch_size: int = 500) -> RecomputeAllResult:
    """Recompute reputation scores for all packages in batches."""
    db = get_task_session()
    try:
        pkg_ids = db.execute(
            select(Package.id).limit(batch_size)
        ).scalars().all()

        for pid in pkg_ids:
            compute_reputation_score.delay(pid)

        total: int = len(pkg_ids)
        logger.info("Queued score recomputation for %d packages", total)
        return asdict(RecomputeAllResult(queued=total))
    finally:
        remove_task_session()
