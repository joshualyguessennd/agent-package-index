CREATE TABLE IF NOT EXISTS package_version (
    id              BIGSERIAL PRIMARY KEY,
    package_id      BIGINT NOT NULL REFERENCES package(id) ON DELETE CASCADE,
    version         TEXT NOT NULL,
    release_date    TIMESTAMPTZ,
    dependencies    JSONB,
    dep_count       INTEGER NOT NULL DEFAULT 0,
    size_bytes      BIGINT,
    is_yanked       BOOLEAN NOT NULL DEFAULT FALSE,
    is_latest       BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_package_version_package_id
    ON package_version (package_id);

CREATE INDEX IF NOT EXISTS idx_package_version_is_latest
    ON package_version (package_id) WHERE is_latest = TRUE;

CREATE TABLE IF NOT EXISTS download_stat (
    id              BIGSERIAL PRIMARY KEY,
    package_id      BIGINT NOT NULL REFERENCES package(id) ON DELETE CASCADE,
    period          TEXT NOT NULL,
    date            DATE NOT NULL,
    download_count  BIGINT NOT NULL DEFAULT 0,
    UNIQUE (package_id, period, date)
);

CREATE INDEX IF NOT EXISTS idx_download_stat_package_id
    ON download_stat (package_id);

DO $$ BEGIN
    CREATE TYPE severity_type AS ENUM ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS vulnerability (
    id              BIGSERIAL PRIMARY KEY,
    package_id      BIGINT NOT NULL REFERENCES package(id) ON DELETE CASCADE,
    cve_id          TEXT,
    advisory_id     TEXT,
    severity        severity_type,
    summary         TEXT,
    affected_versions TEXT,
    fixed_version   TEXT,
    published_at    TIMESTAMPTZ,
    source          TEXT,
    source_url      TEXT
);

CREATE INDEX IF NOT EXISTS idx_vulnerability_package_id
    ON vulnerability (package_id);
