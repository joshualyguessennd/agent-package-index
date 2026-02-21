"""Unit tests for the scoring engine."""

from datetime import datetime, timedelta, timezone

from app.schemas.scoring import (
    DependencyInput,
    LicenseInput,
    MaintainerInput,
    MaintenanceInput,
    PopularityInput,
    ScoringInput,
    VulnerabilityInput,
)
from app.services.scoring import (
    compute_reputation,
    score_dependency,
    score_license,
    score_maintainer,
    score_maintenance,
    score_popularity,
    score_vulnerability,
)


class TestScoreMaintenance:
    def test_recent_release_scores_high(self) -> None:
        inp = MaintenanceInput(
            latest_release_at=datetime.now(tz=timezone.utc) - timedelta(days=7),
            release_count=20,
            latest_version="2.0.0",
        )
        result = score_maintenance(inp)
        assert result.score > 0.6
        assert result.name == "maintenance"

    def test_old_release_scores_low(self) -> None:
        inp = MaintenanceInput(
            latest_release_at=datetime.now(tz=timezone.utc) - timedelta(days=1500),
            release_count=2,
            latest_version="0.1.0",
        )
        result = score_maintenance(inp)
        assert result.score < 0.4

    def test_no_release_date_scores_minimum(self) -> None:
        inp = MaintenanceInput()
        result = score_maintenance(inp)
        assert result.score > 0.0
        assert result.score < 0.2

    def test_mature_version_gets_bonus(self) -> None:
        base = MaintenanceInput(
            latest_release_at=datetime.now(tz=timezone.utc) - timedelta(days=30),
            release_count=10,
            latest_version="0.9.0",
        )
        mature = MaintenanceInput(
            latest_release_at=datetime.now(tz=timezone.utc) - timedelta(days=30),
            release_count=10,
            latest_version="1.0.0",
        )
        assert score_maintenance(mature).score > score_maintenance(base).score


class TestScoreVulnerability:
    def test_no_vulns_perfect_score(self) -> None:
        inp = VulnerabilityInput()
        result = score_vulnerability(inp)
        assert result.score == 1.0

    def test_critical_vuln_heavy_penalty(self) -> None:
        inp = VulnerabilityInput(total_count=1, critical_count=1)
        result = score_vulnerability(inp)
        assert result.score == 0.7

    def test_multiple_vulns_stack(self) -> None:
        inp = VulnerabilityInput(
            total_count=5, critical_count=1, high_count=2, medium_count=2
        )
        result = score_vulnerability(inp)
        assert result.score < 0.5

    def test_unpatched_extra_penalty(self) -> None:
        patched = VulnerabilityInput(total_count=1, high_count=1, unpatched_count=0)
        unpatched = VulnerabilityInput(total_count=1, high_count=1, unpatched_count=1)
        assert score_vulnerability(patched).score > score_vulnerability(unpatched).score

    def test_score_clamps_at_zero(self) -> None:
        inp = VulnerabilityInput(
            total_count=20, critical_count=10, unpatched_count=10
        )
        result = score_vulnerability(inp)
        assert result.score == 0.0


class TestScoreDependency:
    def test_zero_deps_high_score(self) -> None:
        inp = DependencyInput(direct_dep_count=0)
        result = score_dependency(inp)
        assert result.score > 0.7

    def test_many_deps_lower_score(self) -> None:
        few = DependencyInput(direct_dep_count=3)
        many = DependencyInput(direct_dep_count=50)
        assert score_dependency(few).score > score_dependency(many).score

    def test_high_dep_quality_helps(self) -> None:
        low_q = DependencyInput(direct_dep_count=10, avg_dep_maintenance_score=0.2)
        high_q = DependencyInput(direct_dep_count=10, avg_dep_maintenance_score=0.9)
        assert score_dependency(high_q).score > score_dependency(low_q).score


class TestScorePopularity:
    def test_zero_downloads(self) -> None:
        inp = PopularityInput(monthly_downloads=0)
        result = score_popularity(inp)
        assert result.score == 0.0

    def test_hundred_downloads(self) -> None:
        inp = PopularityInput(monthly_downloads=100)
        result = score_popularity(inp)
        assert 0.2 <= result.score <= 0.35

    def test_ten_thousand_downloads(self) -> None:
        inp = PopularityInput(monthly_downloads=10_000)
        result = score_popularity(inp)
        assert 0.4 <= result.score <= 0.6

    def test_one_million_downloads(self) -> None:
        inp = PopularityInput(monthly_downloads=1_000_000)
        result = score_popularity(inp)
        assert 0.7 <= result.score <= 0.85

    def test_hundred_million_downloads(self) -> None:
        inp = PopularityInput(monthly_downloads=100_000_000)
        result = score_popularity(inp)
        assert result.score >= 0.9


class TestScoreMaintainer:
    def test_default_maintainer(self) -> None:
        inp = MaintainerInput()
        result = score_maintainer(inp)
        assert result.score > 0.0

    def test_prolific_high_quality(self) -> None:
        inp = MaintainerInput(maintainer_package_count=15, avg_maintainer_quality=0.9)
        result = score_maintainer(inp)
        assert result.score > 0.7


class TestScoreLicense:
    def test_mit_license(self) -> None:
        inp = LicenseInput(license_name="MIT")
        result = score_license(inp)
        assert result.score == 1.0

    def test_apache_license(self) -> None:
        inp = LicenseInput(license_name="Apache-2.0")
        result = score_license(inp)
        assert result.score == 1.0

    def test_gpl_license(self) -> None:
        inp = LicenseInput(license_name="GPL-3.0")
        result = score_license(inp)
        assert result.score == 0.4

    def test_agpl_license(self) -> None:
        inp = LicenseInput(license_name="AGPL-3.0")
        result = score_license(inp)
        assert result.score == 0.3

    def test_unknown_license(self) -> None:
        inp = LicenseInput(license_name=None)
        result = score_license(inp)
        assert result.score == 0.2

    def test_bsd_license(self) -> None:
        inp = LicenseInput(license_name="BSD-3-Clause")
        result = score_license(inp)
        assert result.score == 0.9


class TestComputeReputation:
    def test_full_reputation(self) -> None:
        inp = ScoringInput(
            maintenance=MaintenanceInput(
                latest_release_at=datetime.now(tz=timezone.utc) - timedelta(days=30),
                release_count=25,
                latest_version="2.31.0",
            ),
            vulnerability=VulnerabilityInput(),
            dependency=DependencyInput(direct_dep_count=4),
            popularity=PopularityInput(monthly_downloads=50_000_000),
            maintainer=MaintainerInput(
                maintainer_package_count=5, avg_maintainer_quality=0.7
            ),
            license=LicenseInput(license_name="Apache-2.0"),
        )
        result = compute_reputation(inp)
        assert 0.0 <= result.overall_score <= 1.0
        assert len(result.dimensions) == 6
        assert result.maintenance > 0.0
        assert result.vulnerability == 1.0
        assert result.license == 1.0

    def test_all_dimensions_present(self) -> None:
        result = compute_reputation(ScoringInput())
        dim_names: list[str] = [d.name for d in result.dimensions]
        assert "maintenance" in dim_names
        assert "vulnerability" in dim_names
        assert "dependency" in dim_names
        assert "popularity" in dim_names
        assert "maintainer" in dim_names
        assert "license" in dim_names

    def test_weights_sum_to_one(self) -> None:
        result = compute_reputation(ScoringInput())
        total_weight: float = sum(d.weight for d in result.dimensions)
        assert abs(total_weight - 1.0) < 0.001
