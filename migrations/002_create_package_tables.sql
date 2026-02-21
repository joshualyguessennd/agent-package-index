-- Enable trigram extension for fuzzy name matching
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Registry enum
DO $$ BEGIN
    CREATE TYPE registry_type AS ENUM ('pypi', 'npm');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS package (
    id              BIGSERIAL PRIMARY KEY,
    registry        registry_type NOT NULL,
    name            TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    summary         TEXT,
    description     TEXT,
    homepage_url    TEXT,
    repository_url  TEXT,
    documentation_url TEXT,
    license         TEXT,
    keywords        TEXT[],
    classifiers     TEXT[],
    requires_python TEXT,
    author          TEXT,
    author_email    TEXT,
    maintainers     JSONB,
    first_release_at TIMESTAMPTZ,
    latest_release_at TIMESTAMPTZ,
    is_deprecated   BOOLEAN NOT NULL DEFAULT FALSE,
    is_yanked       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    crawled_at      TIMESTAMPTZ,
    search_vector   tsvector,
    UNIQUE (registry, normalized_name)
);

-- GIN index on tsvector for full-text search
CREATE INDEX IF NOT EXISTS idx_package_search_vector
    ON package USING GIN (search_vector);

-- GIN trigram index on normalized_name for fuzzy matching
CREATE INDEX IF NOT EXISTS idx_package_normalized_name_trgm
    ON package USING GIN (normalized_name gin_trgm_ops);

-- Index on registry for filtered queries
CREATE INDEX IF NOT EXISTS idx_package_registry
    ON package (registry);

-- Trigger function: build weighted tsvector from name, summary, keywords, description
CREATE OR REPLACE FUNCTION package_search_vector_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('english', COALESCE(NEW.name, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.summary, '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(array_to_string(NEW.keywords, ' '), '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(NEW.description, '')), 'C');
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_package_search_vector ON package;
CREATE TRIGGER trg_package_search_vector
    BEFORE INSERT OR UPDATE ON package
    FOR EACH ROW EXECUTE FUNCTION package_search_vector_update();
