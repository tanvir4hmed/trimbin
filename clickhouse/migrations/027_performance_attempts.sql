-- Logical performances within immutable recordings. Human boundary revisions
-- remain operational Firestore documents; machine proposals are immutable.
CREATE TABLE IF NOT EXISTS performance_attempts
(
    attempt_id UUID,
    run_id UUID,
    project_id UInt32,
    clip_id UUID,
    start_s Float64,
    end_s Float64,
    action String,
    observation String,
    interpretation String,
    recommendation String,
    confidence Float32,
    intent String,
    starts_before_window Bool,
    ends_after_window Bool,
    evidence_segment_ids Array(UUID),
    model_id LowCardinality(String),
    prompt_version LowCardinality(String),
    occurred_at DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(occurred_at)
ORDER BY (project_id, clip_id, run_id, attempt_id);

GRANT SELECT ON performance_attempts TO trimbin_reader;
