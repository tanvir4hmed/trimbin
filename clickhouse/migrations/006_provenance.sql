-- Where a row came from, and why that has to be visible.
--
-- The archive holds two kinds of data with two entirely different standings.
--
--   Real: footage that was actually measured, decisions an agent actually made,
--         overrides a person actually recorded.
--
--   Synthetic: rows generated to demonstrate that the queries stay fast over
--         millions of records. Useful for exactly that and worthless as
--         evidence of anything else.
--
-- Mixing them and publishing the result as an accuracy figure is the failure
-- this file exists to make structurally impossible. A number computed over
-- generated rows measures the generator, not the system, and presenting one as
-- the other is the single thing a product built on not overclaiming cannot do.
--
-- The separation is by project id rather than a column, because a column can be
-- forgotten in a WHERE clause and a range cannot be joined across by accident.

-- Synthetic projects live at and above this id. Real work uses ids below it.
--   SELECT ... WHERE project_id < 900000   -- real only
--   SELECT ... WHERE project_id >= 900000  -- the scale demonstration

DROP VIEW IF EXISTS accuracy;

CREATE VIEW accuracy AS
WITH per_shot AS (
    SELECT
        project_id,
        group_id,
        subgroup_id,
        argMinIf(margin, decided_at, decided_by = 'agent')  AS agent_margin,
        argMinIf(clip_id, decided_at, decided_by = 'agent') AS agent_pick,
        argMax(clip_id, decided_at)                         AS current_pick,
        countIf(decided_by = 'human')                       AS human_touches
    FROM decisions
    -- Real work only. Generated rows would make this figure a measurement of
    -- the random number generator that produced them.
    WHERE outcome = 'selected' AND project_id < 900000
    GROUP BY project_id, group_id, subgroup_id
),
classified AS (
    SELECT
        agent_margin >= 0.15                             AS was_confident,
        human_touches > 0 AND current_pick != agent_pick AS overturned
    FROM per_shot
)
SELECT
    round(100 * countIf(was_confident AND NOT overturned)
              / nullIf(countIf(was_confident), 0), 1)         AS decision_accuracy_pct,
    countIf(was_confident)                                    AS confident_decisions,
    countIf(was_confident AND overturned)                     AS confident_overturned,
    countIf(NOT was_confident)                                AS flagged_for_review,
    round(100 * countIf(NOT was_confident AND overturned)
              / nullIf(countIf(NOT was_confident), 0), 1)     AS flagged_changed_pct,
    round(100 * countIf(was_confident) / nullIf(count(), 0), 1) AS auto_decided_pct,
    count()                                                   AS shots_total
FROM classified;


-- What the archive holds, counted honestly and separately.
--
-- The synthetic figures are worth publishing — they are the reason to believe
-- the engine choice — but only when labelled as what they are.
CREATE VIEW IF NOT EXISTS corpus AS
SELECT
    countIf(project_id < 900000)                                        AS real_clips,
    countIf(project_id >= 900000)                                       AS synthetic_clips,
    countDistinctIf(project_id, project_id < 900000)                    AS real_productions,
    countDistinctIf(project_id, project_id >= 900000)                   AS synthetic_productions,
    countDistinctIf((project_id, group_id), project_id < 900000)        AS real_scenes,
    countDistinctIf((project_id, group_id, subgroup_id),
                    project_id < 900000)                                AS real_shots,
    round(sumIf(duration_ms, project_id < 900000) / 3600000, 2)         AS real_hours,
    round(sumIf(duration_ms, project_id >= 900000) / 3600000, 1)        AS synthetic_hours
FROM clips;


-- The review queue, likewise scoped to real work. A queue full of generated
-- shots would be a queue nobody can act on.
DROP VIEW IF EXISTS review_queue;

CREATE VIEW review_queue AS
SELECT
    d.project_id,
    d.group_id,
    d.subgroup_id,
    argMax(d.clip_id, d.decided_at)              AS leading_clip_id,
    argMax(d.margin, d.decided_at)               AS margin,
    argMax(d.reason, d.decided_at)               AS reason,
    max(d.decided_at)                            AS decided_at,
    argMax(d.decided_by, d.decided_at) = 'human' AS already_reviewed
FROM decisions AS d
WHERE d.outcome = 'selected' AND d.project_id < 900000
GROUP BY d.project_id, d.group_id, d.subgroup_id
HAVING margin < 0.15 AND already_reviewed = 0
ORDER BY margin ASC;
