import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, scoped_session, sessionmaker

from app.config import TestConfig
from app.factory import create_app

# SQLite-compatible DDL for test tables (no ARRAY, ENUM, tsvector)
_SQLITE_SCHEMA: str = """
CREATE TABLE IF NOT EXISTS example (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS package (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    registry TEXT NOT NULL,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    summary TEXT,
    description TEXT,
    homepage_url TEXT,
    repository_url TEXT,
    documentation_url TEXT,
    license TEXT,
    keywords TEXT,
    classifiers TEXT,
    requires_python TEXT,
    author TEXT,
    author_email TEXT,
    maintainers TEXT,
    first_release_at TIMESTAMP,
    latest_release_at TIMESTAMP,
    is_deprecated BOOLEAN NOT NULL DEFAULT 0,
    is_yanked BOOLEAN NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    crawled_at TIMESTAMP,
    search_vector TEXT,
    UNIQUE (registry, normalized_name)
);

CREATE TABLE IF NOT EXISTS package_version (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    package_id INTEGER NOT NULL REFERENCES package(id),
    version TEXT NOT NULL,
    release_date TIMESTAMP,
    dependencies TEXT,
    dep_count INTEGER NOT NULL DEFAULT 0,
    size_bytes INTEGER,
    is_yanked BOOLEAN NOT NULL DEFAULT 0,
    is_latest BOOLEAN NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS download_stat (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    package_id INTEGER NOT NULL REFERENCES package(id),
    period TEXT NOT NULL,
    date TEXT NOT NULL,
    download_count INTEGER NOT NULL DEFAULT 0,
    UNIQUE (package_id, period, date)
);

CREATE TABLE IF NOT EXISTS vulnerability (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    package_id INTEGER NOT NULL REFERENCES package(id),
    cve_id TEXT,
    advisory_id TEXT,
    severity TEXT,
    summary TEXT,
    affected_versions TEXT,
    fixed_version TEXT,
    published_at TIMESTAMP,
    source TEXT,
    source_url TEXT
);

CREATE TABLE IF NOT EXISTS reputation_score (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    package_id INTEGER NOT NULL UNIQUE REFERENCES package(id),
    maintenance REAL NOT NULL DEFAULT 0.0,
    vulnerability REAL NOT NULL DEFAULT 0.0,
    dependency REAL NOT NULL DEFAULT 0.0,
    popularity REAL NOT NULL DEFAULT 0.0,
    maintainer REAL NOT NULL DEFAULT 0.0,
    license REAL NOT NULL DEFAULT 0.0,
    overall_score REAL NOT NULL DEFAULT 0.0,
    score_details TEXT,
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS crawl_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    registry TEXT NOT NULL,
    task_type TEXT NOT NULL,
    cursor TEXT,
    status TEXT NOT NULL DEFAULT 'idle',
    last_run_at TIMESTAMP,
    error_message TEXT
);
"""


@pytest.fixture()
def app():
    app = create_app(config=TestConfig)
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db_engine():
    """Create a fresh in-memory SQLite database with all tables."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    with engine.connect() as conn:
        for stmt in _SQLITE_SCHEMA.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt))
        conn.commit()
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(db_engine) -> Session:
    """Provide a scoped session for tests."""
    session_factory = sessionmaker(bind=db_engine)
    session: scoped_session[Session] = scoped_session(session_factory)
    yield session
    session.remove()


@pytest.fixture()
def seeded_db(db_session) -> Session:
    """Seed the test database with sample packages and scores."""
    db_session.execute(
        text(
            "INSERT INTO package (id, registry, name, normalized_name, summary, "
            "description, license, author) "
            "VALUES (1, 'pypi', 'requests', 'requests', 'Python HTTP for Humans.', "
            "'A simple HTTP library', 'Apache-2.0', 'Kenneth Reitz')"
        )
    )
    db_session.execute(
        text(
            "INSERT INTO package (id, registry, name, normalized_name, summary, "
            "description, license, author) "
            "VALUES (2, 'npm', 'express', 'express', "
            "'Fast, unopinionated, minimalist web framework', "
            "'Web framework for Node.js', 'MIT', 'TJ Holowaychuk')"
        )
    )
    db_session.execute(
        text(
            "INSERT INTO package (id, registry, name, normalized_name, summary, "
            "description, license, author) "
            "VALUES (3, 'pypi', 'flask', 'flask', "
            "'A simple framework for building complex web applications.', "
            "'Flask is a lightweight WSGI web application framework.', 'BSD-3-Clause', "
            "'Armin Ronacher')"
        )
    )
    db_session.execute(
        text(
            "INSERT INTO package_version (package_id, version, dep_count, is_latest) "
            "VALUES (1, '2.31.0', 4, 1)"
        )
    )
    db_session.execute(
        text(
            "INSERT INTO package_version (package_id, version, dep_count, is_latest) "
            "VALUES (2, '4.18.2', 5, 1)"
        )
    )
    db_session.execute(
        text(
            "INSERT INTO reputation_score (package_id, maintenance, vulnerability, "
            "dependency, popularity, maintainer, license, overall_score) "
            "VALUES (1, 0.85, 0.95, 0.8, 0.75, 0.6, 1.0, 0.845)"
        )
    )
    db_session.execute(
        text(
            "INSERT INTO reputation_score (package_id, maintenance, vulnerability, "
            "dependency, popularity, maintainer, license, overall_score) "
            "VALUES (2, 0.7, 0.9, 0.6, 0.8, 0.7, 1.0, 0.78)"
        )
    )
    db_session.execute(
        text(
            "INSERT INTO vulnerability (package_id, cve_id, advisory_id, severity, "
            "summary, fixed_version, source) "
            "VALUES (1, 'CVE-2023-32681', 'GHSA-j8r2-6x86-q33e', 'MEDIUM', "
            "'Unintended leak of Proxy-Authorization header', '2.31.0', 'osv')"
        )
    )
    db_session.execute(
        text(
            "INSERT INTO download_stat (package_id, period, date, download_count) "
            "VALUES (1, 'last_month', '2024-01-15', 50000000)"
        )
    )
    db_session.commit()
    return db_session
