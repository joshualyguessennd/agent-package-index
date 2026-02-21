CREATE TABLE IF NOT EXISTS reputation_score (
    id              BIGSERIAL PRIMARY KEY,
    package_id      BIGINT NOT NULL UNIQUE REFERENCES package(id) ON DELETE CASCADE,
    maintenance     FLOAT NOT NULL DEFAULT 0.0,
    vulnerability   FLOAT NOT NULL DEFAULT 0.0,
    dependency      FLOAT NOT NULL DEFAULT 0.0,
    popularity      FLOAT NOT NULL DEFAULT 0.0,
    maintainer      FLOAT NOT NULL DEFAULT 0.0,
    license         FLOAT NOT NULL DEFAULT 0.0,
    overall_score   FLOAT NOT NULL DEFAULT 0.0,
    score_details   JSONB,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reputation_score_package_id
    ON reputation_score (package_id);

CREATE INDEX IF NOT EXISTS idx_reputation_score_overall
    ON reputation_score (overall_score DESC);

CREATE TABLE IF NOT EXISTS crawl_state (
    id              BIGSERIAL PRIMARY KEY,
    registry        registry_type NOT NULL,
    task_type       TEXT NOT NULL,
    cursor          TEXT,
    status          TEXT NOT NULL DEFAULT 'idle',
    last_run_at     TIMESTAMPTZ,
    error_message   TEXT
);
