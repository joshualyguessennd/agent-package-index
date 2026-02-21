"""Search query builder for the package index.

Uses raw SQL via text() for PostgreSQL-specific full-text search functions
(ts_rank_cd, plainto_tsquery, similarity) that have no ORM equivalent.
"""

from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.search import SearchParams, SearchResponse, SearchResultItem


@dataclass
class SearchBindParams:
    """Bind parameters for the search SQL query."""

    query: str
    limit: int
    offset: int
    min_score: float
    registry: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Convert to dict for SQLAlchemy text() bind params."""
        result: dict[str, object] = {
            "query": self.query,
            "limit": self.limit,
            "offset": self.offset,
            "min_score": self.min_score,
        }
        if self.registry is not None:
            result["registry"] = self.registry
        return result


@dataclass
class CountBindParams:
    """Bind parameters for the count SQL query."""

    query: str
    min_score: float
    registry: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Convert to dict for SQLAlchemy text() bind params."""
        result: dict[str, object] = {
            "query": self.query,
            "min_score": self.min_score,
        }
        if self.registry is not None:
            result["registry"] = self.registry
        return result


@dataclass
class BuiltQuery:
    """A built SQL query with its bind parameters."""

    sql: str
    bind: dict[str, object] = field(default_factory=dict)


def build_search_query(params: SearchParams) -> BuiltQuery:
    """Build the search SQL query with parameterized filters.

    Combines:
    - ts_rank_cd on search_vector (60% weight)
    - reputation overall_score (30% weight)
    - trigram similarity on normalized_name (10% weight)
    """
    bind_params = SearchBindParams(
        query=params.q,
        limit=params.limit,
        offset=params.offset,
        min_score=params.min_score,
        registry=params.registry,
    )

    registry_filter: str = ""
    if params.registry:
        registry_filter = "AND p.registry = :registry"

    sql: str = f"""
        SELECT
            p.id,
            p.registry,
            p.name,
            p.summary,
            COALESCE(r.overall_score, 0) AS overall_score,
            COALESCE(r.maintenance, 0) AS maintenance,
            COALESCE(r.vulnerability, 0) AS vulnerability,
            COALESCE(r.dependency, 0) AS dependency,
            COALESCE(r.popularity, 0) AS popularity,
            COALESCE(r.maintainer, 0) AS maintainer_score,
            COALESCE(r.license, 0) AS license_score,
            (
                0.6 * ts_rank_cd(
                    p.search_vector,
                    plainto_tsquery('english', :query)
                ) +
                0.3 * COALESCE(r.overall_score, 0) +
                0.1 * similarity(p.normalized_name, :query)
            ) AS rank
        FROM package p
        LEFT JOIN reputation_score r ON r.package_id = p.id
        WHERE p.search_vector @@ plainto_tsquery('english', :query)
            AND COALESCE(r.overall_score, 0) >= :min_score
            {registry_filter}
        ORDER BY rank DESC
        LIMIT :limit OFFSET :offset
    """

    return BuiltQuery(sql=sql, bind=bind_params.to_dict())


def build_count_query(params: SearchParams) -> BuiltQuery:
    """Build the count query for total results."""
    bind_params = CountBindParams(
        query=params.q,
        min_score=params.min_score,
        registry=params.registry,
    )

    registry_filter: str = ""
    if params.registry:
        registry_filter = "AND p.registry = :registry"

    sql: str = f"""
        SELECT COUNT(*)
        FROM package p
        LEFT JOIN reputation_score r ON r.package_id = p.id
        WHERE p.search_vector @@ plainto_tsquery('english', :query)
            AND COALESCE(r.overall_score, 0) >= :min_score
            {registry_filter}
    """

    return BuiltQuery(sql=sql, bind=bind_params.to_dict())


def execute_search(db: Session, params: SearchParams) -> SearchResponse:
    """Execute a search query and return a structured response."""
    search_q = build_search_query(params)
    count_q = build_count_query(params)

    rows = db.execute(text(search_q.sql), search_q.bind).fetchall()
    count_row = db.execute(text(count_q.sql), count_q.bind).fetchone()
    total: int = count_row[0] if count_row else 0

    items: list[SearchResultItem] = [
        SearchResultItem(
            id=row[0],
            registry=row[1],
            name=row[2],
            summary=row[3],
            overall_score=float(row[4]),
            maintenance=float(row[5]),
            vulnerability=float(row[6]),
            dependency=float(row[7]),
            popularity=float(row[8]),
            maintainer_score=float(row[9]),
            license_score=float(row[10]),
            rank=float(row[11]),
        )
        for row in rows
    ]

    return SearchResponse(
        items=items,
        total=total,
        limit=params.limit,
        offset=params.offset,
    )
