# Agent Package Index

A trusted, agent-readable package index that crawls PyPI and npm, scores every package on reputation, and exposes a semantic search API. Built so that AI agents can answer questions like *"find me a well-maintained Python library for PDF parsing with no known CVEs"* backed by real data.

## Why

Agents that write or recommend code need to pick dependencies. Public registries tell you what exists, but not whether it's safe, maintained, or popular enough to trust. This system bridges that gap by continuously crawling package metadata, cross-referencing vulnerability databases, and computing a multi-dimensional reputation score for each package.

## Architecture

```
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│   Flask API  │      │ Celery Beat  │      │   PostgreSQL │
│  (search,    │◄────►│  (scheduled  │◄────►│  (packages,  │
│   detail,    │      │   crawlers)  │      │   scores,    │
│   batch)     │      │              │      │   vulns)     │
└──────────────┘      └──────┬───────┘      └──────────────┘
                             │
                    ┌────────┼────────┐
                    ▼        ▼        ▼
                  PyPI     npm      OSV
                  API      API    (vulns)
```

- **Flask** serves the JSON API (search, package detail, batch lookup, stats)
- **Celery + Redis** runs background crawlers on a schedule and computes scores
- **PostgreSQL** stores packages with full-text search via `tsvector` and trigram similarity (`pg_trgm`)
- **SQLAlchemy 2.0** ORM for all database access

## Reputation Scoring

Each package receives a score from 0.0 to 1.0 across six dimensions, combined into a weighted overall score:

| Dimension | Weight | What it measures |
|-----------|--------|------------------|
| Maintenance | 25% | Days since last release (exponential decay), release frequency, version maturity (>=1.0) |
| Vulnerability | 25% | Count and severity of CVEs from OSV, unpatched penalty |
| Dependency | 15% | Direct dependency count (fewer = better), average dep quality |
| Popularity | 15% | Monthly downloads on a log10 scale (100 -> 0.25, 10k -> 0.5, 1M -> 0.75) |
| Maintainer | 10% | Track record of the maintainer across packages |
| License | 10% | Permissiveness (MIT/Apache = 1.0, GPL = 0.4, unknown = 0.2) |

The scoring engine is pure functions with no database access — all inputs flow through typed schemas.

## API Endpoints

All endpoints are under `/api/packages`.

### `GET /api/packages/search`

Semantic search combining full-text ranking (60%), reputation score (30%), and name similarity (10%).

| Param | Default | Description |
|-------|---------|-------------|
| `q` | required | Search query |
| `registry` | all | Filter by `pypi` or `npm` |
| `min_score` | 0.0 | Minimum reputation score |
| `limit` | 20 | Results per page (max 100) |
| `offset` | 0 | Pagination offset |

### `GET /api/packages/<registry>/<name>`

Full package detail: metadata, latest version, reputation breakdown, vulnerabilities, download stats.

### `GET /api/packages/<registry>/<name>/versions`

Paginated version list with release dates, dep counts, sizes, and yank status.

### `POST /api/packages/batch`

Batch lookup by list of `{registry, name}` pairs. Returns reputation summaries for each.

### `GET /api/packages/stats`

Index overview: total packages, counts by registry, score distribution, last crawl time.

## Project Structure

```
app/
  api/
    packages.py          # API endpoints (search, detail, batch, stats, versions)
  schemas/
    search.py            # Search params, result items, detail response
    scoring.py           # Scoring input/output schemas
    tasks.py             # Celery task result schemas
    package.py           # Package metadata schemas
    model_gen.py         # Model generator schemas
  services/
    scoring.py           # Pure-function reputation scoring engine
    search.py            # SQL query builder for full-text search
    crawlers/
      pypi_client.py     # PyPI JSON API + Simple Index client
      npm_client.py      # npm registry + CouchDB changes client
      osv_client.py      # OSV vulnerability database client
      stats_client.py    # Download stats clients (pypistats, npm)
  tasks/
    crawl_pypi.py        # PyPI list, detail, and download crawlers
    crawl_npm.py         # npm list, detail, and download crawlers
    crawl_vulnerabilities.py  # OSV vulnerability crawler
    compute_scores.py    # Score computation tasks
    orchestrator.py      # Full crawl pipeline
  models.py              # Auto-generated SQLAlchemy ORM models
  factory.py             # Flask application factory
  worker.py              # Celery app with Beat schedule
  config.py              # Configuration from environment

migrations/              # SQL migration files (run in order)
scripts/
  generate_models.py     # Generates models.py from migration SQL

tests/
  test_scoring.py        # Scoring engine unit tests
  test_search.py         # Search query builder + endpoint tests
  test_package_detail.py # Detail, stats, batch, versions endpoint tests
  test_crawl_pypi.py     # PyPI client parsing tests
  test_crawl_npm.py      # npm client parsing tests
  fixtures/              # Trimmed real API responses for test parsing
```

## Setup

### Prerequisites

- Python 3.12+
- PostgreSQL with `pg_trgm` extension
- Redis

### Install

```bash
cp .env.example .env        # edit DATABASE_URL, REDIS_URL
make install                # poetry install
make db-create              # createdb agent_system
make migrate                # apply SQL migrations
make generate-models        # regenerate models.py from migrations
```

### Run

```bash
make run                    # Flask API on :5000
make worker                 # Celery worker + Beat scheduler
```

### Crawl

```bash
make crawl                  # trigger a one-off full crawl pipeline
```

The Beat scheduler also runs crawls automatically:
- Package lists every 6 hours
- Download stats daily at 2 AM
- Vulnerabilities weekly
- Score recomputation daily at 5 AM

### Test

```bash
make test                   # pytest
make lint                   # ruff check
make fmt                    # ruff format
```

## Configuration

Set via environment variables or `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://localhost:5432/agent_system` | PostgreSQL connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis broker for Celery |
| `SECRET_KEY` | `dev-secret-key` | Flask secret key |
| `PYPI_CRAWL_RATE_LIMIT` | `50` | PyPI requests per second |
| `NPM_CRAWL_RATE_LIMIT` | `50` | npm requests per second |
| `OSV_API_URL` | `https://api.osv.dev/v1` | OSV vulnerability API base URL |
