-- A newly analysed slate is a proposal, not the canonical home of a clip.
-- Operational readers only see a human-settled placement. The inbox continues
-- to show the newest proposal, including clean matches, until verification.

DROP VIEW IF EXISTS current_clip_placement;
DROP VIEW IF EXISTS settled_placement;

CREATE VIEW settled_placement AS
SELECT
    project_id,
    clip_id,
    argMax(group_id, placement_order) AS group_id,
    argMax(subgroup_id, placement_order) AS subgroup_id,
    argMax(take_no, placement_order) AS take_no,
    argMax(source, placement_order) AS source,
    argMax(actor, placement_order) AS actor,
    max(occurred_at) AS decided_at
FROM
(
    SELECT *, tuple(occurred_at, event_id) AS placement_order
    FROM placements
    WHERE state IN ('settled', 'ignored')
)
GROUP BY project_id, clip_id;

CREATE VIEW current_clip_placement AS
SELECT
    c.* EXCEPT (group_id, subgroup_id, take_no),
    if(s.clip_id = toUUID('00000000-0000-0000-0000-000000000000'), c.group_id, s.group_id) AS group_id,
    if(s.clip_id = toUUID('00000000-0000-0000-0000-000000000000'), c.subgroup_id, s.subgroup_id) AS subgroup_id,
    if(s.clip_id = toUUID('00000000-0000-0000-0000-000000000000') OR s.take_no = 0, c.take_no, s.take_no) AS take_no
FROM clips AS c
LEFT JOIN settled_placement AS s
    ON s.project_id = c.project_id AND s.clip_id = c.clip_id
LEFT JOIN current_placement AS proposed
    ON proposed.project_id = c.project_id AND proposed.clip_id = c.clip_id
WHERE NOT (
    proposed.state = 'open'
    AND s.clip_id = toUUID('00000000-0000-0000-0000-000000000000')
);

GRANT SELECT ON settled_placement TO trimbin_reader;
GRANT SELECT ON current_clip_placement TO trimbin_reader;
