-- Views over an append-only log.
--
-- Because decisions are never edited, "what is selected now" is a question about
-- the newest row rather than a lookup. That is cheap in ClickHouse but it is
-- asked on every page load, so the answers that matter are kept materialized.

-- ---------------------------------------------------------------------------
-- Current selection per shot.
--
-- ReplacingMergeTree keeps the latest row per key, which is exactly the semantics
-- we want: a human override lands after the agent's pick and wins. `argMax` in
-- the reader still guards against reading before a merge has run.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS current_selection
(
    project_id      UInt32,
    group_id        UInt32,
    subgroup_id     UInt32,
    clip_id         UUID,
    decided_at      DateTime64(3),
    decided_by      Enum8('agent' = 1, 'human' = 2),
    actor_id        String,
    score           Float32,
    margin          Float32,
    reason          String,
    in_point_s      Float32,
    out_point_s     Float32
)
ENGINE = ReplacingMergeTree(decided_at)
ORDER BY (project_id, group_id, subgroup_id);

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_current_selection
TO current_selection
AS
SELECT
    project_id, group_id, subgroup_id, clip_id, decided_at,
    decided_by, actor_id, score, margin, reason, in_point_s, out_point_s
FROM decisions
WHERE outcome = 'selected';


-- ---------------------------------------------------------------------------
-- The review queue — the product's front door.
--
-- A shot needs a person when the top two takes were technically equivalent, when
-- nothing was good enough, or when the grouping itself was guessed rather than
-- read. Everything else was decided and deserves no one's attention.
-- ---------------------------------------------------------------------------

CREATE VIEW IF NOT EXISTS review_queue AS
SELECT
    d.project_id,
    d.group_id,
    d.subgroup_id,
    argMax(d.clip_id, d.decided_at)   AS leading_clip_id,
    argMax(d.margin, d.decided_at)    AS margin,
    argMax(d.reason, d.decided_at)    AS reason,
    max(d.decided_at)                 AS decided_at,
    argMax(d.decided_by, d.decided_at) = 'human' AS already_reviewed
FROM decisions AS d
WHERE d.outcome = 'selected'
GROUP BY d.project_id, d.group_id, d.subgroup_id
HAVING margin < 0.15 AND already_reviewed = 0
ORDER BY margin ASC;


-- ---------------------------------------------------------------------------
-- Accuracy, published openly.
--
-- The override rate is split deliberately. Disagreement on a flagged call is the
-- system working as designed — those were handed to a person on purpose.
-- Disagreement on a confident call is a real error. One combined number would
-- flatter us and inform nobody.
-- ---------------------------------------------------------------------------

CREATE VIEW IF NOT EXISTS accuracy_summary AS
WITH per_shot AS (
    SELECT
        project_id,
        group_id,
        subgroup_id,
        argMin(margin, decided_at)     AS original_margin,
        countIf(decided_by = 'human')  AS human_decisions
    FROM decisions
    WHERE outcome = 'selected'
    GROUP BY project_id, group_id, subgroup_id
)
SELECT
    count()                                                       AS shots_total,
    countIf(original_margin >= 0.15)                              AS decided_confidently,
    countIf(original_margin <  0.15)                              AS sent_for_review,

    -- The honest error signal: the system was sure, a human disagreed.
    round(100 * countIf(original_margin >= 0.15 AND human_decisions > 0)
              / nullIf(countIf(original_margin >= 0.15), 0), 1)    AS override_rate_confident_pct,

    -- Expected to be high. High is success here, not failure.
    round(100 * countIf(original_margin < 0.15 AND human_decisions > 0)
              / nullIf(countIf(original_margin < 0.15), 0), 1)     AS override_rate_flagged_pct,

    -- The product's central claim, measured rather than asserted.
    round(100 * countIf(original_margin >= 0.15) / nullIf(count(), 0), 1) AS auto_decided_pct
FROM per_shot;
