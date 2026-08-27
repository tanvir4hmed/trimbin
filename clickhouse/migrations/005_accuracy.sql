-- Accuracy, defined precisely enough to be worth publishing.
--
-- A single "accuracy" figure is easy to produce and usually dishonest, so the
-- definition is written here rather than in a slide, and the page computes it
-- from this view. Anyone can read what the number means.
--
-- THE HEADLINE
--
--   Decision accuracy = confident decisions that stood
--                     / confident decisions
--
-- A decision is confident when the leading take won by more than the review
-- threshold. It stood if no human later replaced it. That ratio is the honest
-- claim: when the system was sure, how often was it right?
--
-- WHAT IT DOES NOT MEAN
--
--   Overrides on flagged shots are excluded from the numerator and denominator
--   entirely. Those shots were handed to a person on purpose, and counting a
--   human choosing between two near-identical takes as a system error would be
--   measuring the product working and calling it a fault.
--
-- THE WEAKNESS, STATED
--
--   Confident decisions are not systematically reviewed — the queue only
--   surfaces close calls. So "not overturned" is weaker evidence than "verified
--   correct": some of those shots were never looked at closely. The eval set
--   exists precisely because this number cannot carry the whole claim, and both
--   are published side by side.

CREATE VIEW IF NOT EXISTS accuracy AS
WITH per_shot AS (
    SELECT
        project_id,
        group_id,
        subgroup_id,
        -- The system's original position, before any human touched it.
        argMinIf(margin, decided_at, decided_by = 'agent')       AS agent_margin,
        argMinIf(clip_id, decided_at, decided_by = 'agent')      AS agent_pick,
        -- What stands now.
        argMax(clip_id, decided_at)                              AS current_pick,
        argMax(decided_by, decided_at)                           AS decided_by_last,
        countIf(decided_by = 'human')                            AS human_touches
    FROM decisions
    WHERE outcome = 'selected'
    GROUP BY project_id, group_id, subgroup_id
),
classified AS (
    SELECT
        agent_margin >= 0.15                                     AS was_confident,
        -- Overturned means a human looked and chose differently. A human who
        -- confirmed the same take is agreement, not correction, so comparing
        -- the clip matters rather than merely counting human involvement.
        human_touches > 0 AND current_pick != agent_pick         AS overturned
    FROM per_shot
)
SELECT
    -- The headline.
    round(100 * countIf(was_confident AND NOT overturned)
              / nullIf(countIf(was_confident), 0), 1)            AS decision_accuracy_pct,

    -- Its ingredients, so the figure can be checked rather than trusted.
    countIf(was_confident)                                       AS confident_decisions,
    countIf(was_confident AND overturned)                        AS confident_overturned,

    -- The other half of the story: shots deliberately handed to a person.
    countIf(NOT was_confident)                                   AS flagged_for_review,
    round(100 * countIf(NOT was_confident AND overturned)
              / nullIf(countIf(NOT was_confident), 0), 1)        AS flagged_changed_pct,

    -- The product's central claim.
    round(100 * countIf(was_confident) / nullIf(count(), 0), 1)  AS auto_decided_pct,
    count()                                                      AS shots_total
FROM classified;


-- ---------------------------------------------------------------------------
-- Ground truth, from footage shot with faults planted on purpose.
--
-- The headline above measures agreement with editors. This measures agreement
-- with reality: we know there is camera shake at 4.2 seconds because we put it
-- there. It is the harder number and the smaller sample, and publishing both is
-- the only honest way to present either.
--
-- Populated by the eval harness. Empty until Phase 3, and the page says so
-- rather than showing a hopeful zero.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS eval_results
(
    run_at          DateTime,
    fixture_id      String COMMENT 'Which planted clip',
    axis            LowCardinality(String) COMMENT 'stability, exposure, continuity, completion…',

    expected        UInt8 COMMENT '1 = a fault was planted on this axis',
    detected        UInt8 COMMENT '1 = the system reported one',

    -- A fault found in the wrong second is not a fault found. Timecodes are how
    -- findings become links, so a finding pointing at the wrong moment is
    -- useless to the editor who clicks it.
    expected_start_s Float32 DEFAULT 0,
    detected_start_s Float32 DEFAULT 0,
    within_tolerance UInt8 DEFAULT 0,

    model_id        LowCardinality(String),
    prompt_version  LowCardinality(String)
)
ENGINE = MergeTree
ORDER BY (run_at, axis, fixture_id);


CREATE VIEW IF NOT EXISTS eval_accuracy AS
SELECT
    axis,
    count()                                                      AS cases,

    -- Missed faults and false alarms are not equally bad and are never summed.
    -- A missed problem reaches the cut; a false alarm costs ten seconds of an
    -- editor's attention.
    countIf(expected = 1 AND detected = 0)                       AS missed,
    countIf(expected = 0 AND detected = 1)                       AS false_alarms,

    round(100 * countIf(expected = 1 AND detected = 1)
              / nullIf(countIf(expected = 1), 0), 1)             AS recall_pct,
    round(100 * countIf(expected = 1 AND detected = 1)
              / nullIf(countIf(detected = 1), 0), 1)             AS precision_pct,
    round(100 * countIf(expected = 1 AND detected = 1 AND within_tolerance = 1)
              / nullIf(countIf(expected = 1 AND detected = 1), 0), 1) AS timecode_accuracy_pct,

    max(run_at)                                                  AS last_run
FROM eval_results
GROUP BY axis
ORDER BY axis;
