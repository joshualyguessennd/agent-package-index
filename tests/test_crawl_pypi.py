"""Tests for PyPI client parsing with fixture JSON (mocked HTTP)."""

import json
from pathlib import Path

import pytest

from app.services.crawlers.pypi_client import PyPIClient

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def pypi_fixture_data() -> dict:
    """Load the PyPI requests fixture."""
    with open(FIXTURES_DIR / "pypi_requests.json") as f:
        return json.load(f)


@pytest.fixture()
def pypi_client() -> PyPIClient:
    return PyPIClient()


class TestPyPIClientParsing:
    def test_parse_package_detail(
        self, pypi_client: PyPIClient, pypi_fixture_data: dict
    ) -> None:
        result = pypi_client._parse_package_detail(pypi_fixture_data)

        assert result.registry == "pypi"
        assert result.name == "requests"
        assert result.normalized_name == "requests"
        assert result.summary == "Python HTTP for Humans."
        assert result.author == "Kenneth Reitz"
        assert result.license == "Apache-2.0"
        assert result.requires_python == ">=3.7"
        assert "http" in result.keywords
        assert len(result.classifiers) == 4
        assert result.homepage_url == "https://requests.readthedocs.io"
        assert result.repository_url == "https://github.com/psf/requests"
        assert result.documentation_url == "https://requests.readthedocs.io"
        assert result.first_release_at is not None
        assert result.latest_release_at is not None
        assert result.latest_release_at >= result.first_release_at

    def test_parse_package_detail_maintainers(
        self, pypi_client: PyPIClient, pypi_fixture_data: dict
    ) -> None:
        result = pypi_client._parse_package_detail(pypi_fixture_data)
        assert len(result.maintainers) == 1
        assert result.maintainers[0].name == "Seth Michael Larson"
        assert result.maintainers[0].email == "sethmlarson@gmail.com"

    def test_parse_versions(
        self, pypi_client: PyPIClient, pypi_fixture_data: dict
    ) -> None:
        versions = pypi_client._parse_versions(pypi_fixture_data)

        assert len(versions) == 2
        latest = next(v for v in versions if v.is_latest)
        assert latest.version == "2.31.0"
        assert latest.dep_count == 4
        assert latest.size_bytes > 0
        assert not latest.is_yanked

    def test_parse_versions_non_latest_has_no_deps(
        self, pypi_client: PyPIClient, pypi_fixture_data: dict
    ) -> None:
        versions = pypi_client._parse_versions(pypi_fixture_data)
        older = next(v for v in versions if v.version == "2.30.0")
        assert older.dep_count == 0
        assert not older.is_latest

    def test_parse_downloads(self, pypi_client: PyPIClient) -> None:
        data: dict = {
            "data": {
                "last_day": 5000,
                "last_week": 35000,
                "last_month": 150000,
            }
        }
        stats = pypi_client._parse_downloads(data)
        assert len(stats) == 3
        monthly = next(s for s in stats if s.period == "last_month")
        assert monthly.download_count == 150000

    def test_normalize_name(self) -> None:
        assert PyPIClient._normalize_name("My-Package") == "my-package"
        assert PyPIClient._normalize_name("my_package") == "my-package"
        assert PyPIClient._normalize_name("my.package") == "my-package"
        assert PyPIClient._normalize_name("My__Package") == "my-package"

    def test_parse_empty_releases(self, pypi_client: PyPIClient) -> None:
        data: dict = {"info": {"name": "empty", "version": "0.1"}, "releases": {}}
        result = pypi_client._parse_package_detail(data)
        assert result.first_release_at is None
        assert result.latest_release_at is None
