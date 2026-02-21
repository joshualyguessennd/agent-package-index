"""Search query builder for the package index.

Uses SQLAlchemy func() for PostgreSQL full-text search functions
(ts_rank_cd, plainto_tsquery, similarity).
"""

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models import Package, ReputationScore
from app.schemas.search import SearchParams, SearchResponse, SearchResultItem


def _tsquery(query: str):
    """Build a plainto_tsquery('english', query) expression."""
    return func.plainto_tsquery("english", query)


def build_search_query(params: SearchParams) -> Select:
    """Build the search ORM query with semantic ranking.

    Combines:
    - ts_rank_cd on search_vector (60% weight)
    - reputation overall_score (30% weight)
    - trigram similarity on normalized_name (10% weight)
    """
    tsq = _tsquery(params.q)

    rank = (
        0.6 * func.ts_rank_cd(Package.search_vector, tsq)
        + 0.3 * func.coalesce(ReputationScore.overall_score, 0)
        + 0.1 * func.similarity(Package.normalized_name, params.q)
    ).label("rank")

    stmt = (
        select(
            Package.id,
            Package.registry,
            Package.name,
            Package.summary,
            func.coalesce(ReputationScore.overall_score, 0).label("overall_score"),
            func.coalesce(ReputationScore.maintenance, 0).label("maintenance"),
            func.coalesce(ReputationScore.vulnerability, 0).label("vulnerability"),
            func.coalesce(ReputationScore.dependency, 0).label("dependency"),
            func.coalesce(ReputationScore.popularity, 0).label("popularity"),
            func.coalesce(ReputationScore.maintainer, 0).label("maintainer_score"),
            func.coalesce(ReputationScore.license, 0).label("license_score"),
            rank,
        )
        .outerjoin(ReputationScore, ReputationScore.package_id == Package.id)
        .where(Package.search_vector.op("@@")(tsq))
        .where(func.coalesce(ReputationScore.overall_score, 0) >= params.min_score)
        .order_by(rank.desc())
        .limit(params.limit)
        .offset(params.offset)
    )

    if params.registry:
        stmt = stmt.where(Package.registry == params.registry)

    return stmt


def build_count_query(params: SearchParams) -> Select:
    """Build the count query for total results."""
    tsq = _tsquery(params.q)

    stmt = (
        select(func.count())
        .select_from(Package)
        .outerjoin(ReputationScore, ReputationScore.package_id == Package.id)
        .where(Package.search_vector.op("@@")(tsq))
        .where(func.coalesce(ReputationScore.overall_score, 0) >= params.min_score)
    )

    if params.registry:
        stmt = stmt.where(Package.registry == params.registry)

    return stmt


def execute_search(db: Session, params: SearchParams) -> SearchResponse:
    """Execute a search query and return a structured response."""
    search_stmt = build_search_query(params)
    count_stmt = build_count_query(params)

    rows = db.execute(search_stmt).fetchall()
    total: int = db.execute(count_stmt).scalar_one()

    items: list[SearchResultItem] = [
        SearchResultItem(
            id=row.id,
            registry=row.registry.value if hasattr(row.registry, 'value') else str(row.registry),
            name=row.name,
            summary=row.summary,
            overall_score=float(row.overall_score),
            maintenance=float(row.maintenance),
            vulnerability=float(row.vulnerability),
            dependency=float(row.dependency),
            popularity=float(row.popularity),
            maintainer_score=float(row.maintainer_score),
            license_score=float(row.license_score),
            rank=float(row.rank),
        )
        for row in rows
    ]

    return SearchResponse(
        items=items,
        total=total,
        limit=params.limit,
        offset=params.offset,
    )
