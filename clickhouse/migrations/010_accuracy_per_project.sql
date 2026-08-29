-- The same accuracy arithmetic, one row per project.
--
-- A single figure across every production is the wrong shape for this system.
-- Accuracy on a scene of locked-off interiors and accuracy on a handheld chase
-- are different claims, and averaging them produces a number that describes
-- neither. An editor asking "how well does this work on my footage?" cannot be
-- answered by a mean over somebody else's.
--
-- The definition is unchanged, deliberately: the same WITH clauses, the same
-- confidence threshold, the same exclusion of generated rows. Two views that
-- compute accuracy differently would eventually disagree, and the one nobody
-- checked would be the one on the page.

CREATE VIEW IF NOT EXISTS accuracy_by_project AS
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
    WHERE outcome = 'selected' AND project_id < 900000
    GROUP BY project_id, group_id, subgroup_id
),
classified AS (
    SELECT
        project_id,
        agent_margin >= 0.15                             AS was_confident,
        human_touches > 0 AND current_pick != agent_pick AS overturned
    FROM per_shot
)
SELECT
    project_id,
    round(100 * countIf(was_confident AND NOT overturned)
              / nullIf(countIf(was_confident), 0), 1)         AS decision_accuracy_pct,
    countIf(was_confident)                                    AS confident_decisions,
    countIf(was_confident AND overturned)                     AS confident_overturned,
    countIf(NOT was_confident)                                AS flagged_for_review,
    round(100 * countIf(NOT was_confident AND overturned)
              / nullIf(countIf(NOT was_confident), 0), 1)     AS flagged_changed_pct,
    round(100 * countIf(was_confident) / nullIf(count(), 0), 1) AS auto_decided_pct,
    count()                                                   AS shots_total
FROM classified
GROUP BY project_id
ORDER BY project_id;


-- What each project holds, for the selector beside the figure.
--
-- The counts are the context the percentage needs. A project with four shots
-- and one with four hundred both produce a percentage, and only one of them
-- means anything — a reader who cannot see which is which cannot weigh either.
CREATE VIEW IF NOT EXISTS project_corpus AS
SELECT
    project_id,
    count()                                        AS clips,
    countDistinct(group_id)                        AS scenes,
    countDistinct((group_id, subgroup_id))         AS setups,
    countIf(status = 'failed')                     AS unusable,
    round(sum(duration_ms) / 3600000, 3)           AS footage_hours,
    max(ingested_at)                               AS last_ingest
FROM real_clips
GROUP BY project_id
ORDER BY project_id;
