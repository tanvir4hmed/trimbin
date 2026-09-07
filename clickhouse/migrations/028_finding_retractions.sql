-- Retraction is a new event, not deletion or rewriting an earlier judgement.
ALTER TABLE finding_events ADD COLUMN IF NOT EXISTS retracts_event_id UUID DEFAULT toUUID('00000000-0000-0000-0000-000000000000');
ALTER TABLE finding_events ADD COLUMN IF NOT EXISTS restored_action String DEFAULT '';

CREATE OR REPLACE VIEW current_finding_state AS
SELECT project_id, clip_id, finding_id,
    argMax(event_id, finding_order) AS event_id,
    argMax(run_id, finding_order) AS run_id,
    argMax(revision, finding_order) AS revision,
    argMax(if(action='human_retracted', restored_action, action), finding_order) AS action,
    argMax(code, finding_order) AS code,
    argMax(detail, finding_order) AS detail,
    argMax(severity, finding_order) AS severity,
    argMax(start_s, finding_order) AS start_s,
    argMax(end_s, finding_order) AS end_s,
    argMax(evidence_segment_ids, finding_order) AS evidence_segment_ids,
    argMax(sources, finding_order) AS sources,
    argMax(supersedes_event_id, finding_order) AS supersedes_event_id,
    argMax(actor_id, finding_order) AS actor_id,
    argMax(actor_role, finding_order) AS actor_role,
    max(occurred_at) AS occurred_at
FROM (SELECT *, tuple(revision, occurred_at, event_id) AS finding_order FROM finding_events)
GROUP BY project_id, clip_id, finding_id;
