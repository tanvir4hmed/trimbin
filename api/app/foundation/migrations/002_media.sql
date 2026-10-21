CREATE TABLE project_members (
    project_id bigint NOT NULL REFERENCES projects(id),
    email text NOT NULL,
    role text NOT NULL CHECK(role IN ('owner','editor','viewer')),
    PRIMARY KEY(project_id,email)
);
CREATE TABLE media_sources (
    id uuid PRIMARY KEY,
    project_id bigint NOT NULL REFERENCES projects(id),
    root_alias text NOT NULL,
    relative_path text NOT NULL,
    filename text NOT NULL,
    job_id uuid NOT NULL REFERENCES jobs(id),
    fingerprint text,
    metadata jsonb,
    derivatives jsonb,
    duplicate_of uuid REFERENCES media_sources(id),
    stage text NOT NULL DEFAULT 'queued',
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE(project_id, root_alias, relative_path)
);
CREATE INDEX media_fingerprints ON media_sources(project_id, fingerprint);
CREATE TABLE media_uploads (
    id uuid PRIMARY KEY,
    project_id bigint NOT NULL REFERENCES projects(id),
    filename text NOT NULL,
    expected_bytes bigint NOT NULL CHECK(expected_bytes > 0),
    received_bytes bigint NOT NULL DEFAULT 0 CHECK(received_bytes >= 0),
    chunk_hashes jsonb NOT NULL DEFAULT '[]',
    created_by text NOT NULL,
    source_id uuid REFERENCES media_sources(id),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK(received_bytes <= expected_bytes)
);
