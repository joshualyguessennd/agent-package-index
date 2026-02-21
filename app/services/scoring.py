"""Pure-function reputation scoring engine. No DB access — all inputs via schemas."""

import math
from datetime import datetime, timezone

from app.schemas.scoring import (
    DependencyInput,
    DimensionScore,
    LicenseInput,
    MaintainerInput,
    MaintenanceInput,
    PopularityInput,
    ReputationResult,
    ScoringInput,
    VulnerabilityInput,
)

# Dimension weights (must sum to 1.0)
WEIGHTS: dict[str, float] = {
    "maintenance": 0.25,
    "vulnerability": 0.25,
    "dependency": 0.15,
    "popularity": 0.15,
    "maintainer": 0.10,
    "license": 0.10,
}

# License permissiveness map
LICENSE_SCORES: dict[str, float] = {
    "mit": 1.0,
    "apache-2.0": 1.0,
    "apache 2.0": 1.0,
    "bsd-2-clause": 0.9,
    "bsd-3-clause": 0.9,
    "bsd": 0.9,
    "isc": 0.9,
    "mpl-2.0": 0.7,
    "lgpl-2.1": 0.5,
    "lgpl-3.0": 0.5,
    "gpl-2.0": 0.4,
    "gpl-3.0": 0.4,
    "gpl": 0.4,
    "agpl-3.0": 0.3,
    "agpl": 0.3,
    "unlicense": 0.8,
    "cc0-1.0": 0.8,
}

DEFAULT_LICENSE_SCORE: float = 0.2


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    """Clamp a value between low and high."""
    return max(low, min(high, value))


def score_maintenance(inp: MaintenanceInput) -> DimensionScore:
    """Score based on release recency, frequency, and version maturity.

    - Days since last release: exponential decay over 2 years (730 days)
    - Release frequency bonus: more releases = better maintained
    - Version maturity: >= 1.0 gets a bonus
    """
    now: datetime = datetime.now(tz=timezone.utc)
    recency_score: float = 0.0

    if inp.latest_release_at is not None:
        latest = inp.latest_release_at
        if latest.tzinfo is None:
            latest = latest.replace(tzinfo=timezone.utc)
        days_since: float = (now - latest).total_seconds() / 86400
        # Exponential decay: score=1.0 at 0 days, ~0.37 at 730 days, ~0.14 at 1460 days
        recency_score = math.exp(-days_since / 730)
    else:
        recency_score = 0.1

    # Release frequency bonus (capped)
    freq_score: float = _clamp(inp.release_count / 50, 0.0, 0.3)

    # Version maturity bonus
    maturity_bonus: float = 0.0
    if inp.latest_version:
        try:
            major = int(inp.latest_version.split(".")[0])
            if major >= 1:
                maturity_bonus = 0.1
        except (ValueError, IndexError):
            pass

    score: float = _clamp(recency_score * 0.6 + freq_score + maturity_bonus)
    details: str = (
        f"recency={recency_score:.2f}, freq_bonus={freq_score:.2f}, "
        f"maturity={maturity_bonus:.2f}"
    )
    return DimensionScore(
        name="maintenance", score=score, weight=WEIGHTS["maintenance"], details=details
    )


def score_vulnerability(inp: VulnerabilityInput) -> DimensionScore:
    """Score based on vulnerability count and severity. Higher = fewer/less severe vulns.

    Starts at 1.0 and penalizes for each vulnerability by severity.
    Unpatched vulnerabilities incur extra penalty.
    """
    score: float = 1.0

    # Severity penalties
    score -= inp.critical_count * 0.3
    score -= inp.high_count * 0.2
    score -= inp.medium_count * 0.1
    score -= inp.low_count * 0.05

    # Extra penalty for unpatched
    score -= inp.unpatched_count * 0.15

    score = _clamp(score)
    details: str = (
        f"total={inp.total_count}, critical={inp.critical_count}, "
        f"high={inp.high_count}, unpatched={inp.unpatched_count}"
    )
    return DimensionScore(
        name="vulnerability", score=score, weight=WEIGHTS["vulnerability"], details=details
    )


def score_dependency(inp: DependencyInput) -> DimensionScore:
    """Score based on dependency count and quality. Fewer deps = better.

    - 0 deps → 1.0
    - 5 deps → ~0.8
    - 20 deps → ~0.5
    - 50+ deps → ~0.25
    """
    # Inverse sigmoid-like curve for dep count
    dep_score: float = 1.0 / (1.0 + inp.direct_dep_count / 10.0)

    # Blend with average dependency maintenance quality
    blended: float = dep_score * 0.6 + inp.avg_dep_maintenance_score * 0.4

    score: float = _clamp(blended)
    details: str = (
        f"dep_count={inp.direct_dep_count}, dep_score={dep_score:.2f}, "
        f"avg_dep_quality={inp.avg_dep_maintenance_score:.2f}"
    )
    return DimensionScore(
        name="dependency", score=score, weight=WEIGHTS["dependency"], details=details
    )


def score_popularity(inp: PopularityInput) -> DimensionScore:
    """Score based on monthly download count using log10 scale.

    100 → 0.25, 10k → 0.5, 1M → 0.75, 100M → 1.0
    """
    if inp.monthly_downloads <= 0:
        score: float = 0.0
    else:
        log_val: float = math.log10(inp.monthly_downloads)
        # Map: log10(100)=2→0.25, log10(10k)=4→0.5, log10(1M)=6→0.75, log10(100M)=8→1.0
        score = _clamp((log_val - 0.0) / 8.0)

    details: str = f"monthly_downloads={inp.monthly_downloads}"
    return DimensionScore(
        name="popularity", score=score, weight=WEIGHTS["popularity"], details=details
    )


def score_maintainer(inp: MaintainerInput) -> DimensionScore:
    """Score based on maintainer's track record.

    More packages maintained with good quality = higher score.
    """
    # Having 1+ package is baseline; more packages managed well is a bonus
    package_factor: float = _clamp(inp.maintainer_package_count / 20.0, 0.0, 0.3)
    quality_factor: float = inp.avg_maintainer_quality * 0.7

    score: float = _clamp(package_factor + quality_factor)
    details: str = (
        f"packages={inp.maintainer_package_count}, "
        f"avg_quality={inp.avg_maintainer_quality:.2f}"
    )
    return DimensionScore(
        name="maintainer", score=score, weight=WEIGHTS["maintainer"], details=details
    )


def score_license(inp: LicenseInput) -> DimensionScore:
    """Score based on license permissiveness.

    MIT/Apache → 1.0, BSD → 0.9, GPL → 0.4, AGPL → 0.3, unknown → 0.2
    """
    if inp.license_name is None:
        score: float = DEFAULT_LICENSE_SCORE
        details: str = "license=unknown"
    else:
        normalized: str = inp.license_name.strip().lower()
        # Try exact match first, then prefix matching
        score = LICENSE_SCORES.get(normalized, DEFAULT_LICENSE_SCORE)
        if score == DEFAULT_LICENSE_SCORE and normalized not in LICENSE_SCORES:
            for key, val in LICENSE_SCORES.items():
                if key in normalized or normalized in key:
                    score = val
                    break
        details = f"license={inp.license_name}, normalized={normalized}"

    return DimensionScore(
        name="license", score=score, weight=WEIGHTS["license"], details=details
    )


def compute_reputation(inp: ScoringInput) -> ReputationResult:
    """Compute the full reputation score from all dimension inputs.

    Returns a ReputationResult with individual and overall scores.
    """
    dims: list[DimensionScore] = [
        score_maintenance(inp.maintenance),
        score_vulnerability(inp.vulnerability),
        score_dependency(inp.dependency),
        score_popularity(inp.popularity),
        score_maintainer(inp.maintainer),
        score_license(inp.license),
    ]

    overall: float = sum(d.score * d.weight for d in dims)

    return ReputationResult(
        maintenance=dims[0].score,
        vulnerability=dims[1].score,
        dependency=dims[2].score,
        popularity=dims[3].score,
        maintainer=dims[4].score,
        license=dims[5].score,
        overall_score=round(overall, 4),
        dimensions=dims,
    )
