-- Legacy editorial document identities retained in the same PostgreSQL authority.
CREATE TABLE operational_documents (
    path text PRIMARY KEY,
    body jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX operational_documents_parent ON operational_documents ((regexp_replace(path, '/[^/]+$', '')));
ALTER TABLE projects ADD COLUMN state text NOT NULL DEFAULT 'active';
