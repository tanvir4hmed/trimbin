-- Decisions: every comparison the system ever made, and every human answer to one.
--
-- Append-only, and not because ClickHouse dislikes mutations — though it does.
-- An editor overriding a pick is not a correction to be overwritten. It is new
-- information with an author and a timestamp, and the earlier judgement is the
-- thing this whole product exists to keep. So rows are added, never edited, and
-- "what is selected now" is the newest row.
--
-- This is the table the product is named after.

CREATE TABLE IF NOT EXISTS decisions
(
    -- what was decided about ----------------------------------------------
    project_id       UInt32,
    group_id         UInt32,
    subgroup_id      UInt32,
    clip_id          UUID,
    decided_at       DateTime64(3),

    -- the decision --------------------------------------------------------
    outcome          Enum8('selected' = 1, 'runner_up' = 2, 'not_selected' = 3, 'unusable' = 4),
    score            Float32 DEFAULT 0 COMMENT 'Technical cleanliness only — never a judgement of performance',
    margin           Float32 DEFAULT 0 COMMENT 'Gap to next best. Small margin sends the shot to a person',

    -- why, in language an editor would use --------------------------------
    reason           String,
    reason_code      LowCardinality(String),

    -- timecoded findings ---------------------------------------------------
    -- Editors choose moments inside takes, not whole takes. A finding without a
    -- span cannot become a link, and a finding nobody can jump to is a dead end.
    finding_codes    Array(LowCardinality(String)) DEFAULT [],
    finding_starts_s Array(Float32) DEFAULT [],
    finding_ends_s   Array(Float32) DEFAULT [],

    -- who ------------------------------------------------------------------
    decided_by       Enum8('agent' = 1, 'human' = 2),
    actor_id         String DEFAULT '' COMMENT 'Email for a human, agent name otherwise',

    -- provenance -----------------------------------------------------------
    -- Without these, a decision from two years ago is unreadable: you cannot
    -- tell whether it came from a model you would still trust.
    model_id         LowCardinality(String) DEFAULT '',
    prompt_version   LowCardinality(String) DEFAULT '',
    bracket_round    UInt8 DEFAULT 0 COMMENT 'Which comparison round produced this',
    panel_convened   UInt8 DEFAULT 0 COMMENT '1 = full panel, 0 = fast path',
    run_hash         String DEFAULT '' COMMENT 'Idempotency key — a half-failed batch must not duplicate',

    -- in/out for the assembly ----------------------------------------------
    in_point_s       Float32 DEFAULT 0,
    out_point_s      Float32 DEFAULT 0
)
ENGINE = MergeTree
-- Monthly, for the same reason as clips: the ORDER BY key does the query work,
-- and partitions are for lifecycle operations rather than speed.
PARTITION BY toYYYYMM(decided_at)
ORDER BY (project_id, group_id, subgroup_id, decided_at)
SETTINGS index_granularity = 8192;


-- Supersessions: what a reshoot set aside, and why.
--
-- Separate from decisions because it operates on a whole scene rather than a
-- take, and because a reshoot is a production event worth its own record.
-- Nothing is deleted here either.

CREATE TABLE IF NOT EXISTS supersessions
(
    project_id       UInt32,
    group_id         UInt32,
    superseded_at    DateTime,
    superseded_by    String COMMENT 'Email of the lead editor who made the call',
    reason           String,
    replaced_by_group UInt32 DEFAULT 0 COMMENT '0 when nothing replaced it yet'
)
ENGINE = MergeTree
ORDER BY (project_id, group_id, superseded_at);
