CREATE TABLE evidence_runs (
    id uuid PRIMARY KEY,
    project_id bigint NOT NULL REFERENCES projects(id),
    scope text NOT NULL,
    task text NOT NULL,
    mode text NOT NULL CHECK(mode IN ('fixture','nebius')),
    job_id uuid NOT NULL REFERENCES jobs(id),
    plan jsonb NOT NULL,
    result jsonb,
    published boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX evidence_runs_scope ON evidence_runs(project_id,scope,created_at);
CREATE TABLE evidence_requests (
    project_id bigint NOT NULL REFERENCES projects(id),
    scope text NOT NULL,
    latest_run uuid NOT NULL REFERENCES evidence_runs(id),
    PRIMARY KEY(project_id,scope)
);
CREATE TABLE evidence_items (
    project_id bigint NOT NULL REFERENCES projects(id),
    id uuid NOT NULL,
    source_id uuid NOT NULL REFERENCES media_sources(id),
    body jsonb NOT NULL,
    PRIMARY KEY(project_id,id)
);
CREATE TABLE evidence_run_items (
    run_id uuid NOT NULL REFERENCES evidence_runs(id),
    project_id bigint NOT NULL,
    item_id uuid NOT NULL,
    PRIMARY KEY(run_id,item_id),
    FOREIGN KEY(project_id,item_id) REFERENCES evidence_items(project_id,id)
);
