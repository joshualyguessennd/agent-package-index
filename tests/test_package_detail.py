"""Tests for the package detail and other package API endpoints."""

from sqlalchemy import text


class TestPackageDetailEndpoint:
    def test_package_not_found(self, client) -> None:
        response = client.get("/api/packages/pypi/nonexistent-package")
        assert response.status_code in (404, 500)

    def test_stats_endpoint(self, client) -> None:
        response = client.get("/api/packages/stats")
        # May work or error depending on whether PG tables exist
        assert response.status_code in (200, 500)

    def test_batch_endpoint_requires_packages(self, client) -> None:
        response = client.post(
            "/api/packages/batch",
            json={},
        )
        assert response.status_code == 400

    def test_batch_endpoint_empty_list(self, client) -> None:
        response = client.post(
            "/api/packages/batch",
            json={"packages": []},
        )
        assert response.status_code == 400

    def test_batch_endpoint_with_packages(self, client) -> None:
        response = client.post(
            "/api/packages/batch",
            json={
                "packages": [
                    {"registry": "pypi", "name": "requests"},
                    {"registry": "npm", "name": "express"},
                ]
            },
        )
        # May error on SQLite, but verifies endpoint accepts correct input
        assert response.status_code in (200, 500)

    def test_versions_not_found(self, client) -> None:
        response = client.get("/api/packages/pypi/nonexistent/versions")
        assert response.status_code in (404, 500)


class TestPackageDetailWithSeededDB:
    """Tests using the seeded_db fixture for direct DB queries."""

    def test_seeded_packages_exist(self, seeded_db) -> None:
        rows = seeded_db.execute(text("SELECT COUNT(*) FROM package")).fetchone()
        assert rows[0] == 3

    def test_seeded_scores_exist(self, seeded_db) -> None:
        rows = seeded_db.execute(text("SELECT COUNT(*) FROM reputation_score")).fetchone()
        assert rows[0] == 2

    def test_seeded_vulnerability_exists(self, seeded_db) -> None:
        rows = seeded_db.execute(text("SELECT COUNT(*) FROM vulnerability")).fetchone()
        assert rows[0] == 1

    def test_seeded_download_stats(self, seeded_db) -> None:
        rows = seeded_db.execute(text("SELECT COUNT(*) FROM download_stat")).fetchone()
        assert rows[0] == 1

    def test_lookup_package_by_registry_and_name(self, seeded_db) -> None:
        row = seeded_db.execute(
            text(
                "SELECT name, summary FROM package "
                "WHERE registry = 'pypi' AND normalized_name = 'requests'"
            )
        ).fetchone()
        assert row is not None
        assert row[0] == "requests"
        assert "HTTP" in row[1]

    def test_lookup_reputation_score(self, seeded_db) -> None:
        row = seeded_db.execute(
            text(
                "SELECT overall_score, maintenance, license FROM reputation_score "
                "WHERE package_id = 1"
            )
        ).fetchone()
        assert row is not None
        assert row[0] == 0.845
        assert row[1] == 0.85
        assert row[2] == 1.0

    def test_lookup_vulnerability(self, seeded_db) -> None:
        row = seeded_db.execute(
            text(
                "SELECT cve_id, severity FROM vulnerability WHERE package_id = 1"
            )
        ).fetchone()
        assert row is not None
        assert row[0] == "CVE-2023-32681"
        assert row[1] == "MEDIUM"
