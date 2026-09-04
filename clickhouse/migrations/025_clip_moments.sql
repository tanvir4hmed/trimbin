-- Discrete playable events. Analysis windows remain provenance; search returns
-- these tight spans so an editor asking for an action or line lands on it.

CREATE TABLE IF NOT EXISTS clip_moments
(
    moment_id            UUID,
    run_id               UUID,
    project_id           UInt32,
    clip_id              UUID,
    kind                 LowCardinality(String),
    start_s              Float32,
    end_s                Float32,
    text                 String,
    evidence_segment_ids Array(UUID) DEFAULT [],
    embedding            Array(Float32) DEFAULT arrayWithConstant(768, toFloat32(0)),
    model_id             LowCardinality(String) DEFAULT '',
    prompt_version        LowCardinality(String) DEFAULT '',
    occurred_at           DateTime64(3, 'UTC') DEFAULT now64(3),

    INDEX idx_moment_text text
        TYPE text(tokenizer = 'splitByNonAlpha') GRANULARITY 1,
    INDEX idx_moment_embedding embedding
        TYPE vector_similarity('hnsw', 'cosineDistance', 768) GRANULARITY 1,
    INDEX idx_moment_range (start_s, end_s) TYPE minmax GRANULARITY 4
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(occurred_at)
ORDER BY (project_id, clip_id, run_id, start_s, moment_id);

CREATE VIEW IF NOT EXISTS current_clip_moments AS
SELECT m.*
FROM
(
    SELECT *
    FROM clip_moments
    ORDER BY occurred_at DESC
    LIMIT 1 BY moment_id
) AS m
INNER JOIN current_analysis_runs AS r
    ON r.project_id = m.project_id
   AND r.clip_id = m.clip_id
   AND r.run_id = m.run_id
WHERE r.state = 'completed';

GRANT SELECT ON clip_moments TO trimbin_reader;
GRANT SELECT ON current_clip_moments TO trimbin_reader;
