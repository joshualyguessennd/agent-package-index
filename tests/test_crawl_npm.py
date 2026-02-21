"""Tests for npm client parsing with fixture JSON (mocked HTTP)."""

import json
from pathlib import Path

import pytest

from app.services.crawlers.npm_client import NpmClient

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def npm_fixture_data() -> dict:
    """Load the npm express fixture."""
    with open(FIXTURES_DIR / "npm_express.json") as f:
        return json.load(f)


@pytest.fixture()
def npm_client() -> NpmClient:
    return NpmClient()


class TestNpmClientParsing:
    def test_parse_package_detail(
        self, npm_client: NpmClient, npm_fixture_data: dict
    ) -> None:
        result = npm_client._parse_package_detail(npm_fixture_data)

        assert result.registry == "npm"
        assert result.name == "express"
        assert result.normalized_name == "express"
        assert result.summary == "Fast, unopinionated, minimalist web framework"
        assert result.license == "MIT"
        assert result.author == "TJ Holowaychuk"
        assert result.author_email == "tj@vision-media.ca"
        assert "express" in result.keywords
        assert "framework" in result.keywords
        assert result.homepage_url == "http://expressjs.com/"
        assert result.repository_url is not None
        assert result.first_release_at is not None
        assert result.latest_release_at is not None

    def test_parse_package_detail_maintainers(
        self, npm_client: NpmClient, npm_fixture_data: dict
    ) -> None:
        result = npm_client._parse_package_detail(npm_fixture_data)
        assert len(result.maintainers) == 2
        assert result.maintainers[0].name == "dougwilson"
        assert result.maintainers[0].email == "doug@somethingdoug.com"

    def test_parse_versions(
        self, npm_client: NpmClient, npm_fixture_data: dict
    ) -> None:
        versions = npm_client._parse_versions(npm_fixture_data)

        assert len(versions) == 2
        latest = next(v for v in versions if v.is_latest)
        assert latest.version == "4.18.2"
        assert latest.dep_count == 5
        assert latest.size_bytes == 214000
        assert not latest.is_yanked

    def test_parse_versions_older(
        self, npm_client: NpmClient, npm_fixture_data: dict
    ) -> None:
        versions = npm_client._parse_versions(npm_fixture_data)
        older = next(v for v in versions if v.version == "4.18.1")
        assert older.dep_count == 4
        assert not older.is_latest

    def test_parse_versions_dependencies_format(
        self, npm_client: NpmClient, npm_fixture_data: dict
    ) -> None:
        versions = npm_client._parse_versions(npm_fixture_data)
        latest = next(v for v in versions if v.is_latest)
        assert any("accepts" in d for d in latest.dependencies)
        assert any("body-parser" in d for d in latest.dependencies)

    def test_parse_downloads(self, npm_client: NpmClient) -> None:
        data: dict = {
            "downloads": 5000000,
            "start": "2024-01-01",
            "end": "2024-01-31",
        }
        stats = npm_client._parse_downloads(data, "last-month")
        assert len(stats) == 1
        assert stats[0].download_count == 5000000
        assert stats[0].period == "last-month"
        assert stats[0].date == "2024-01-31"

    def test_parse_detail_readme(
        self, npm_client: NpmClient, npm_fixture_data: dict
    ) -> None:
        result = npm_client._parse_package_detail(npm_fixture_data)
        assert result.description is not None
        assert "Express" in result.description

    def test_parse_detail_no_author(self, npm_client: NpmClient) -> None:
        data: dict = {
            "name": "test-pkg",
            "dist-tags": {"latest": "1.0.0"},
            "versions": {"1.0.0": {"license": "MIT"}},
            "time": {},
            "maintainers": [],
        }
        result = npm_client._parse_package_detail(data)
        assert result.author is None
        assert result.author_email is None
