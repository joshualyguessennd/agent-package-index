"""Schemas for the reputation scoring engine."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class MaintenanceInput:
    """Inputs for computing the maintenance dimension score."""

    latest_release_at: datetime | None = None
    first_release_at: datetime | None = None
    release_count: int = 0
    latest_version: str | None = None


@dataclass
class VulnerabilityInput:
    """Inputs for computing the vulnerability dimension score."""

    total_count: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    unpatched_count: int = 0


@dataclass
class DependencyInput:
    """Inputs for computing the dependency dimension score."""

    direct_dep_count: int = 0
    avg_dep_maintenance_score: float = 0.5


@dataclass
class PopularityInput:
    """Inputs for computing the popularity dimension score."""

    monthly_downloads: int = 0


@dataclass
class MaintainerInput:
    """Inputs for computing the maintainer dimension score."""

    maintainer_package_count: int = 0
    avg_maintainer_quality: float = 0.5


@dataclass
class LicenseInput:
    """Inputs for computing the license dimension score."""

    license_name: str | None = None


@dataclass
class ScoringInput:
    """All inputs needed to compute a full reputation score."""

    maintenance: MaintenanceInput = field(default_factory=MaintenanceInput)
    vulnerability: VulnerabilityInput = field(default_factory=VulnerabilityInput)
    dependency: DependencyInput = field(default_factory=DependencyInput)
    popularity: PopularityInput = field(default_factory=PopularityInput)
    maintainer: MaintainerInput = field(default_factory=MaintainerInput)
    license: LicenseInput = field(default_factory=LicenseInput)


@dataclass
class DimensionScore:
    """A single scored dimension with its weight."""

    name: str
    score: float
    weight: float
    details: str = ""


@dataclass
class ReputationResult:
    """Full reputation score result for a package."""

    maintenance: float = 0.0
    vulnerability: float = 0.0
    dependency: float = 0.0
    popularity: float = 0.0
    maintainer: float = 0.0
    license: float = 0.0
    overall_score: float = 0.0
    dimensions: list[DimensionScore] = field(default_factory=list)
