-- The query that answers "why ClickHouse?"
--
-- At a hundred clips any store would do. These run against millions of rows, and
-- each combines things that usually live in three different systems: vector
-- similarity, full-text filtering, and analytical aggregation. Doing all three in
-- one engine is the architectural claim; these are the proof.
--
-- Run with the seed corpus loaded. Timings are printed by the client.

-- ---------------------------------------------------------------------------
-- 1. Hybrid retrieval — the Archivist's actual query path.
--
--    "alternate shots for the rainy window scene under 4 seconds"
--
--    Three constraints, three mechanisms, one pass:
--      meaning   → vector similarity over the multimodal embedding
--      wording   → text index on the description
--      hard fact → minmax index on duration
-- ---------------------------------------------------------------------------

SELECT
    c.group_id,
    c.subgroup_id,
    c.take_no,
    c.description,
    round(c.duration_ms / 1000, 1)              AS seconds,
    d.outcome,
    d.reason,
    round(cosineDistance(c.embedding, {query_vector:Array(Float32)}), 4) AS distance
FROM clips AS c
INNER JOIN decisions AS d USING (clip_id)
WHERE c.project_id = {project_id:UInt32}
  AND c.status = 'active'
  AND c.duration_ms < 4000
  AND d.outcome != 'selected'
  AND hasToken(c.description, 'window')
ORDER BY distance ASC
LIMIT 20;


-- ---------------------------------------------------------------------------
-- 2. What the system gets wrong, across the whole archive.
--
--    Aggregation over every decision ever made, grouped by the reason a take
--    lost and split by whether a human later disagreed. This is what feeds the
--    public accuracy page, and it is recomputed live rather than cached — which
--    is only reasonable because the engine makes it cheap.
-- ---------------------------------------------------------------------------

SELECT
    reason_code,
    count()                                             AS occurrences,
    round(avg(score), 3)                                AS mean_score,
    countIf(decided_by = 'human')                       AS human_disagreements,
    round(100 * countIf(decided_by = 'human') / count(), 1) AS disagreement_pct
FROM decisions
WHERE outcome != 'selected'
GROUP BY reason_code
ORDER BY occurrences DESC;


-- ---------------------------------------------------------------------------
-- 3. Institutional memory — the question no production can answer today.
--
--    "Across every production we have ever shot, what did we reject for
--     continuity, and in which scenes?"
--
--    Cheap here, impossible in a project file.
-- ---------------------------------------------------------------------------

SELECT
    project_id,
    countDistinct(group_id)                     AS scenes_affected,
    count()                                     AS takes_lost_to_continuity,
    groupArraySample(3)(reason)                 AS examples
FROM decisions
WHERE reason_code LIKE 'continuity.%'
GROUP BY project_id
ORDER BY takes_lost_to_continuity DESC
LIMIT 25;


-- ---------------------------------------------------------------------------
-- 4. Where deliberation was worth its cost.
--
--    The panel is expensive, so it only convenes on close calls. This asks
--    whether that was the right threshold: did the shots we sent to a panel
--    actually turn out to be the contentious ones?
-- ---------------------------------------------------------------------------

SELECT
    panel_convened,
    count()                                     AS shots,
    round(avg(margin), 4)                       AS mean_margin,
    round(100 * countIf(decided_by = 'human') / count(), 1) AS later_overridden_pct
FROM decisions
WHERE outcome = 'selected'
GROUP BY panel_convened;
