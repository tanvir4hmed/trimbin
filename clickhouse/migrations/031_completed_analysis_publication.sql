-- Partial/retried generations never replace the last complete evidence set.
-- Live task state belongs to Firestore; analysis_runs retains every attempt.
CREATE OR REPLACE VIEW current_analysis_runs AS
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
    max(published_at)                 AS occurred_at
FROM
(
    SELECT *, occurred_at AS published_at, tuple(occurred_at, event_id) AS run_order
    FROM analysis_runs
    WHERE state = 'completed'
)
GROUP BY project_id, clip_id;
