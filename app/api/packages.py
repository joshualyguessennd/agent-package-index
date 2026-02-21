"""API endpoints for the package index."""

import enum
from dataclasses import asdict

from flask import Blueprint, Response, current_app, jsonify, request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    CrawlState,
    DownloadStat,
    Package,
    PackageVersion,
    ReputationScore,
    Vulnerability,
)
from app.schemas.package import Severity
from app.schemas.search import (
    BatchLookupItem,
    DownloadStatItem,
    IndexStats,
    PackageDetailResponse,
    ReputationBreakdown,
    SearchParams,
    VersionListItem,
    VulnerabilityItem,
)
from app.schemas.tasks import BatchLookupResult
from app.services.search import execute_search


def _asdict_enum(obj: object) -> dict:
    """Convert a dataclass to dict, serializing enum values to strings."""
    raw = asdict(obj)
    return _convert_enums(raw)


def _convert_enums(obj: object) -> object:
    if isinstance(obj, dict):
        return {k: _convert_enums(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_convert_enums(v) for v in obj]
    if isinstance(obj, enum.Enum):
        return obj.value
    return obj

bp = Blueprint("packages", __name__)


def _get_db() -> Session:
    return current_app.config["db_session"]


@bp.route("/search", methods=["GET"])
def search_packages() -> tuple[Response, int] | Response:
    """Search packages by query string with semantic ranking."""
    q: str | None = request.args.get("q")
    if not q:
        return jsonify(error="q parameter is required"), 400

    params = SearchParams(
        q=q,
        registry=request.args.get("registry"),
        min_score=float(request.args.get("min_score", 0.0)),
        limit=min(int(request.args.get("limit", 20)), 100),
        offset=int(request.args.get("offset", 0)),
    )

    db: Session = _get_db()
    result = execute_search(db, params)

    return jsonify(
        items=[asdict(item) for item in result.items],
        total=result.total,
        limit=result.limit,
        offset=result.offset,
    )


@bp.route("/<registry>/<name>", methods=["GET"])
def get_package_detail(
    registry: str, name: str
) -> tuple[Response, int] | Response:
    """Get full detail for a specific package."""
    db: Session = _get_db()

    pkg: Package | None = db.execute(
        select(Package).where(
            Package.registry == registry,
            Package.normalized_name == name.lower(),
        )
    ).scalar_one_or_none()

    if not pkg:
        return jsonify(error="package not found"), 404

    # Latest version
    latest_ver: PackageVersion | None = db.execute(
        select(PackageVersion).where(
            PackageVersion.package_id == pkg.id,
            PackageVersion.is_latest.is_(True),
        )
    ).scalar_one_or_none()

    # Reputation
    rep: ReputationScore | None = db.execute(
        select(ReputationScore).where(
            ReputationScore.package_id == pkg.id
        )
    ).scalar_one_or_none()

    reputation: ReputationBreakdown | None = None
    if rep:
        reputation = ReputationBreakdown(
            overall_score=float(rep.overall_score),
            maintenance=float(rep.maintenance),
            vulnerability=float(rep.vulnerability),
            dependency=float(rep.dependency),
            popularity=float(rep.popularity),
            maintainer=float(rep.maintainer),
            license=float(rep.license),
            computed_at=(
                rep.computed_at.isoformat() if rep.computed_at else None
            ),
        )

    # Vulnerabilities
    vuln_rows: list[Vulnerability] = db.execute(
        select(Vulnerability).where(
            Vulnerability.package_id == pkg.id
        )
    ).scalars().all()

    vulnerabilities: list[VulnerabilityItem] = [
        VulnerabilityItem(
            cve_id=v.cve_id,
            advisory_id=v.advisory_id,
            severity=Severity(v.severity.value) if v.severity else None,
            summary=v.summary,
            affected_versions=v.affected_versions,
            fixed_version=v.fixed_version,
            source=v.source,
        )
        for v in vuln_rows
    ]

    # Download stats
    dl_rows: list[DownloadStat] = db.execute(
        select(DownloadStat)
        .where(DownloadStat.package_id == pkg.id)
        .order_by(DownloadStat.date.desc())
        .limit(10)
    ).scalars().all()

    download_stats: list[DownloadStatItem] = [
        DownloadStatItem(
            period=d.period,
            date=str(d.date),
            download_count=d.download_count,
        )
        for d in dl_rows
    ]

    detail = PackageDetailResponse(
        id=pkg.id,
        registry=str(pkg.registry.value),
        name=pkg.name,
        normalized_name=pkg.normalized_name,
        summary=pkg.summary,
        description=pkg.description,
        homepage_url=pkg.homepage_url,
        repository_url=pkg.repository_url,
        documentation_url=pkg.documentation_url,
        license=pkg.license,
        keywords=pkg.keywords or [],
        classifiers=pkg.classifiers or [],
        requires_python=pkg.requires_python,
        author=pkg.author,
        author_email=pkg.author_email,
        latest_version=latest_ver.version if latest_ver else None,
        latest_release_at=(
            pkg.latest_release_at.isoformat()
            if pkg.latest_release_at
            else None
        ),
        is_deprecated=pkg.is_deprecated,
        reputation=reputation,
        vulnerabilities=vulnerabilities,
        download_stats=download_stats,
    )

    return jsonify(_asdict_enum(detail))


@bp.route("/stats", methods=["GET"])
def get_index_stats() -> Response:
    """Get overview statistics for the package index."""
    db: Session = _get_db()

    total: int = db.execute(
        select(func.count()).select_from(Package)
    ).scalar_one()

    registry_rows = db.execute(
        select(Package.registry, func.count())
        .group_by(Package.registry)
    ).all()
    by_registry: dict[str, int] = {
        str(r[0].value): r[1] for r in registry_rows
    }

    # Score distribution via ORM aggregates
    excellent: int = db.execute(
        select(func.count()).select_from(ReputationScore).where(
            ReputationScore.overall_score >= 0.8
        )
    ).scalar_one()
    good: int = db.execute(
        select(func.count()).select_from(ReputationScore).where(
            ReputationScore.overall_score >= 0.6,
            ReputationScore.overall_score < 0.8,
        )
    ).scalar_one()
    fair: int = db.execute(
        select(func.count()).select_from(ReputationScore).where(
            ReputationScore.overall_score >= 0.4,
            ReputationScore.overall_score < 0.6,
        )
    ).scalar_one()
    poor: int = db.execute(
        select(func.count()).select_from(ReputationScore).where(
            ReputationScore.overall_score < 0.4
        )
    ).scalar_one()

    score_distribution: dict[str, int] = {
        "excellent": excellent,
        "good": good,
        "fair": fair,
        "poor": poor,
    }

    crawl_row = db.execute(
        select(func.max(CrawlState.last_run_at))
    ).scalar_one_or_none()
    last_crawl: str | None = (
        crawl_row.isoformat() if crawl_row else None
    )

    stats = IndexStats(
        total_packages=total,
        by_registry=by_registry,
        score_distribution=score_distribution,
        last_crawl_at=last_crawl,
    )
    return jsonify(asdict(stats))


@bp.route("/batch", methods=["POST"])
def batch_lookup() -> tuple[Response, int] | Response:
    """Batch lookup packages by list of {registry, name} pairs."""
    db: Session = _get_db()
    data = request.get_json(force=True)
    packages: list[dict[str, str]] = data.get("packages", [])

    if not packages:
        return jsonify(error="packages list is required"), 400

    items: list[BatchLookupItem] = [
        BatchLookupItem(registry=p["registry"], name=p["name"])
        for p in packages
    ]

    results: list[BatchLookupResult] = []
    for item in items:
        pkg: Package | None = db.execute(
            select(Package).where(
                Package.registry == item.registry,
                Package.normalized_name == item.name.lower(),
            )
        ).scalar_one_or_none()

        if pkg:
            rep: ReputationScore | None = db.execute(
                select(ReputationScore).where(
                    ReputationScore.package_id == pkg.id
                )
            ).scalar_one_or_none()
            results.append(BatchLookupResult(
                registry=item.registry,
                name=pkg.name,
                found=True,
                summary=pkg.summary,
                overall_score=(
                    float(rep.overall_score) if rep else 0.0
                ),
            ))
        else:
            results.append(BatchLookupResult(
                registry=item.registry,
                name=item.name,
                found=False,
            ))

    return jsonify(results=[asdict(r) for r in results])


@bp.route("/<registry>/<name>/versions", methods=["GET"])
def list_versions(
    registry: str, name: str
) -> tuple[Response, int] | Response:
    """List all versions for a package, paginated."""
    db: Session = _get_db()

    limit: int = min(int(request.args.get("limit", 20)), 100)
    offset: int = int(request.args.get("offset", 0))

    pkg: Package | None = db.execute(
        select(Package).where(
            Package.registry == registry,
            Package.normalized_name == name.lower(),
        )
    ).scalar_one_or_none()

    if not pkg:
        return jsonify(error="package not found"), 404

    rows: list[PackageVersion] = db.execute(
        select(PackageVersion)
        .where(PackageVersion.package_id == pkg.id)
        .order_by(PackageVersion.release_date.desc().nulls_last())
        .limit(limit)
        .offset(offset)
    ).scalars().all()

    total: int = db.execute(
        select(func.count()).select_from(PackageVersion).where(
            PackageVersion.package_id == pkg.id
        )
    ).scalar_one()

    versions: list[VersionListItem] = [
        VersionListItem(
            version=r.version,
            release_date=(
                r.release_date.isoformat() if r.release_date else None
            ),
            dep_count=r.dep_count,
            size_bytes=r.size_bytes,
            is_yanked=r.is_yanked,
            is_latest=r.is_latest,
        )
        for r in rows
    ]

    return jsonify(
        versions=[asdict(v) for v in versions],
        total=total,
        limit=limit,
        offset=offset,
    )
