-- Applied under an advisory transaction lock by migrate(). Never edit after release.
CREATE TABLE IF NOT EXISTS projects (
    id bigint PRIMARY KEY,
    name text NOT NULL
);
CREATE TABLE IF NOT EXISTS state_documents (
    project_id bigint NOT NULL REFERENCES projects(id),
    kind text NOT NULL,
    document_id text NOT NULL,
    revision bigint NOT NULL DEFAULT 0 CHECK (revision >= 0),
    body jsonb NOT NULL DEFAULT '{}',
    PRIMARY KEY (project_id, kind, document_id)
);
CREATE TABLE IF NOT EXISTS state_versions (
    project_id bigint NOT NULL,
    kind text NOT NULL,
    document_id text NOT NULL,
    revision bigint NOT NULL CHECK (revision > 0),
    body jsonb NOT NULL,
    actor text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (project_id, kind, document_id, revision),
    FOREIGN KEY (project_id, kind, document_id)
      REFERENCES state_documents(project_id, kind, document_id)
);
CREATE TABLE IF NOT EXISTS command_receipts (
    project_id bigint NOT NULL REFERENCES projects(id),
    actor text NOT NULL,
    command_id uuid NOT NULL,
    request_hash text NOT NULL,
    result jsonb NOT NULL,
    PRIMARY KEY (project_id, actor, command_id)
);
CREATE TABLE IF NOT EXISTS outbox (
    event_id uuid PRIMARY KEY,
    project_id bigint NOT NULL REFERENCES projects(id),
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    delivered_at timestamptz
);
CREATE INDEX IF NOT EXISTS outbox_pending ON outbox(created_at) WHERE delivered_at IS NULL;
CREATE TABLE IF NOT EXISTS jobs (
    id uuid PRIMARY KEY,
    project_id bigint NOT NULL REFERENCES projects(id),
    kind text NOT NULL,
    payload jsonb NOT NULL,
    dedup_key text NOT NULL,
    state text NOT NULL DEFAULT 'queued'
      CHECK (state IN ('queued','running','succeeded','failed','cancelled')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts integer NOT NULL CHECK (max_attempts BETWEEN 1 AND 10),
    lease_token uuid,
    lease_until timestamptz,
    cancel_requested boolean NOT NULL DEFAULT false,
    available_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    result jsonb,
    error_code text,
    UNIQUE(project_id, kind, dedup_key),
    CHECK ((state = 'running') = (lease_token IS NOT NULL AND lease_until IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS jobs_ready ON jobs(available_at, created_at) WHERE state = 'queued';
CREATE INDEX IF NOT EXISTS jobs_expired ON jobs(lease_until) WHERE state = 'running';
