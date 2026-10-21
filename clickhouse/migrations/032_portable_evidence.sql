-- Complete snapshots make replay and out-of-order delivery safe for this bounded PoC.
CREATE TABLE IF NOT EXISTS portable_evidence_snapshots (
    project_id Int64,
    revision UInt64,
    event_id UUID,
    payload String,
    created_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree
ORDER BY (project_id, revision, event_id);

CREATE TABLE IF NOT EXISTS portable_vector_snapshots (
    project_id Int64,
    revision UInt64,
    identity String,
    payload String,
    created_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree
ORDER BY (project_id, revision, identity);

GRANT SELECT ON portable_evidence_snapshots TO trimbin_reader;
GRANT SELECT ON portable_vector_snapshots TO trimbin_reader;
