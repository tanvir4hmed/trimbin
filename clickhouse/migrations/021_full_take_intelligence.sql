-- Full-take intelligence is append-only.
--
-- A run may move from started to completed or failed, and a finding may move
-- from machine-open to human-confirmed/corrected/dismissed. Those are new facts,
-- not UPDATEs to old ones. The views below resolve the current working answer
-- while the base tables keep the evidence and attribution.

CREATE TABLE IF NOT EXISTS analysis_runs
(
    event_id         UUID,
    run_id           UUID,
    run_key          String COMMENT 'Idempotency key for clip + prompt + window contract',
    project_id       UInt32,
    clip_id          UUID,
    state            LowCardinality(String) COMMENT 'started | completed | failed',
    duration_s       Float32 DEFAULT 0,
    covered_until_s  Float32 DEFAULT 0,
    window_count     UInt16 DEFAULT 0,
    segment_count    UInt16 DEFAULT 0,
    finding_count    UInt16 DEFAULT 0,
    model_id         LowCardinality(String) DEFAULT '',
    prompt_version   LowCardinality(String) DEFAULT '',
    error            String DEFAULT '',
    occurred_at      DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(occurred_at)
ORDER BY (project_id, clip_id, run_key, occurred_at, event_id);

CREATE VIEW IF NOT EXISTS current_analysis_runs AS
SELECT
    project_id,
    clip_id,
    argMax(run_id, run_order)          AS run_id,
    argMax(run_key, run_order)         AS run_key,
    argMax(state, run_order)           AS state,
    argMax(duration_s, run_order)      AS duration_s,
    argMax(covered_until_s, run_order) AS covered_until_s,
    argMax(window_count, run_order)    AS window_count,
    argMax(segment_count, run_order)   AS segment_count,
    argMax(finding_count, run_order)   AS finding_count,
    argMax(model_id, run_order)        AS model_id,
    argMax(prompt_version, run_order)  AS prompt_version,
    argMax(error, run_order)           AS error,
    max(occurred_at)                   AS occurred_at
FROM
(
    SELECT *, tuple(occurred_at, event_id) AS run_order
    FROM analysis_runs
)
GROUP BY project_id, clip_id;

CREATE TABLE IF NOT EXISTS clip_segments
(
    segment_id       UUID,
    run_id           UUID,
    project_id       UInt32,
    clip_id          UUID,
    window_index     UInt16,
    start_s          Float32,
    end_s            Float32,
    description      String DEFAULT '',
    transcript       String DEFAULT '',
    actions          Array(String) DEFAULT [],
    objects          Array(String) DEFAULT [],
    speakers         Array(String) DEFAULT [],
    shot_size        LowCardinality(String) DEFAULT '',
    camera_motion    LowCardinality(String) DEFAULT '',
    embedding        Array(Float32) DEFAULT arrayWithConstant(768, toFloat32(0)),
    model_id         LowCardinality(String) DEFAULT '',
    prompt_version   LowCardinality(String) DEFAULT '',
    occurred_at      DateTime64(3, 'UTC') DEFAULT now64(3),

    INDEX idx_segment_embedding embedding
        TYPE vector_similarity('hnsw', 'cosineDistance', 768) GRANULARITY 1,
    INDEX idx_segment_description description
        TYPE text(tokenizer = 'splitByNonAlpha') GRANULARITY 1,
    INDEX idx_segment_range (start_s, end_s) TYPE minmax GRANULARITY 4
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(occurred_at)
ORDER BY (project_id, clip_id, run_id, start_s, segment_id);

CREATE VIEW IF NOT EXISTS current_clip_segments AS
SELECT s.*
FROM
(
    SELECT *
    FROM clip_segments
    ORDER BY occurred_at DESC
    LIMIT 1 BY segment_id
) AS s
INNER JOIN current_analysis_runs AS r
    ON r.project_id = s.project_id
   AND r.clip_id = s.clip_id
   AND r.run_id = s.run_id
WHERE r.state = 'completed';

-- clips.description is a legacy mutable column in a table whose grouping is in
-- the sort key. Do not run ALTER...UPDATE after analysis. This read model is the
-- current description, derived from the immutable segment descriptions.
CREATE VIEW IF NOT EXISTS clip_analysis_summary AS
SELECT
    project_id,
    clip_id,
    any(run_id) AS run_id,
    arrayStringConcat(groupArray(description), ' ') AS description,
    min(start_s) AS start_s,
    max(end_s) AS end_s,
    count() AS segments
FROM current_clip_segments
GROUP BY project_id, clip_id;

CREATE TABLE IF NOT EXISTS finding_events
(
    event_id            UUID,
    finding_id          UUID,
    run_id              UUID,
    project_id          UInt32,
    clip_id             UUID,
    revision            UInt32,
    action              LowCardinality(String)
        COMMENT 'machine_open | human_confirmed | human_dismissed | human_corrected | human_range_adjusted',
    code                LowCardinality(String),
    detail              String DEFAULT '',
    severity            LowCardinality(String) DEFAULT 'attention',
    start_s             Float32,
    end_s               Float32,
    evidence_segment_ids Array(UUID) DEFAULT [],
    sources             Array(String) DEFAULT [],
    supersedes_event_id UUID DEFAULT toUUID('00000000-0000-0000-0000-000000000000'),
    actor_id            String DEFAULT '',
    actor_role          LowCardinality(String) DEFAULT '',
    model_id            LowCardinality(String) DEFAULT '',
    prompt_version      LowCardinality(String) DEFAULT '',
    occurred_at         DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(occurred_at)
ORDER BY (project_id, clip_id, finding_id, revision, occurred_at, event_id);

CREATE VIEW IF NOT EXISTS current_finding_state AS
SELECT
    project_id,
    clip_id,
    finding_id,
    argMax(event_id, finding_order)             AS event_id,
    argMax(run_id, finding_order)               AS run_id,
    argMax(revision, finding_order)             AS revision,
    argMax(action, finding_order)               AS action,
    argMax(code, finding_order)                 AS code,
    argMax(detail, finding_order)               AS detail,
    argMax(severity, finding_order)             AS severity,
    argMax(start_s, finding_order)              AS start_s,
    argMax(end_s, finding_order)                AS end_s,
    argMax(evidence_segment_ids, finding_order) AS evidence_segment_ids,
    argMax(sources, finding_order)              AS sources,
    argMax(supersedes_event_id, finding_order)  AS supersedes_event_id,
    argMax(actor_id, finding_order)              AS actor_id,
    argMax(actor_role, finding_order)            AS actor_role,
    max(occurred_at)                             AS occurred_at
FROM
(
    SELECT *, tuple(revision, occurred_at, event_id) AS finding_order
    FROM finding_events
)
GROUP BY project_id, clip_id, finding_id;

CREATE VIEW IF NOT EXISTS current_findings AS
SELECT f.*
FROM current_finding_state AS f
INNER JOIN current_analysis_runs AS r
    ON r.project_id = f.project_id
   AND r.clip_id = f.clip_id
   AND r.run_id = f.run_id
WHERE r.state = 'completed' AND f.action != 'human_dismissed';

GRANT SELECT ON analysis_runs TO trimbin_reader;
GRANT SELECT ON current_analysis_runs TO trimbin_reader;
GRANT SELECT ON clip_segments TO trimbin_reader;
GRANT SELECT ON current_clip_segments TO trimbin_reader;
GRANT SELECT ON clip_analysis_summary TO trimbin_reader;
GRANT SELECT ON finding_events TO trimbin_reader;
GRANT SELECT ON current_finding_state TO trimbin_reader;
GRANT SELECT ON current_findings TO trimbin_reader;
