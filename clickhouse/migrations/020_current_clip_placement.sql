-- Deterministic, append-only placement resolution.
--
-- `at` was a second-resolution timestamp. Two actions in the same second could
-- therefore tie in argMax and make "current" depend on merge order. Keep it for
-- compatibility, but give every new event a millisecond clock and a UUID.
ALTER TABLE placements
    ADD COLUMN IF NOT EXISTS event_id UUID
    DEFAULT toUUID('00000000-0000-0000-0000-000000000000');

ALTER TABLE placements
    ADD COLUMN IF NOT EXISTS occurred_at DateTime64(3, 'UTC')
    DEFAULT toDateTime64(at, 3, 'UTC');

-- placement_inbox depends on current_placement, so remove views from the leaves
-- inward and recreate them below. No stored rows are touched.
DROP VIEW IF EXISTS placement_inbox;
DROP VIEW IF EXISTS current_clip_placement;
DROP VIEW IF EXISTS current_placement;

CREATE VIEW current_placement AS
SELECT
    project_id,
    clip_id,
    argMax(group_id, placement_order)        AS group_id,
    argMax(subgroup_id, placement_order)     AS subgroup_id,
    argMax(take_no, placement_order)         AS take_no,
    argMax(source, placement_order)          AS source,
    argMax(actor, placement_order)           AS actor,
    argMax(confidence, placement_order)      AS confidence,
    argMax(state, placement_order)           AS state,
    argMax(slate_raw, placement_order)       AS slate_raw,
    argMax(declared_group, placement_order)  AS declared_group,
    argMax(declared_shot, placement_order)   AS declared_shot,
    argMax(detail, placement_order)          AS detail,
    max(occurred_at)                         AS decided_at,
    argMax(event_id, placement_order)        AS event_id
FROM
(
    SELECT
        *,
        tuple(
            occurred_at,
            event_id,
            cityHash64(
                toString(group_id), toString(subgroup_id), toString(take_no),
                source, actor, state, detail
            )
        ) AS placement_order
    FROM placements
)
GROUP BY project_id, clip_id;

CREATE VIEW placement_inbox AS
SELECT * FROM current_placement WHERE state = 'open';

-- This is the canonical operational clip relation. A clip without placement
-- history falls back to where it was ingested; once a placement exists, every
-- screen sees the resolved scene/shot/take without mutating the clips sort key.
CREATE VIEW current_clip_placement AS
SELECT
    c.* EXCEPT (group_id, subgroup_id, take_no),
    if(
        p.clip_id = toUUID('00000000-0000-0000-0000-000000000000'),
        c.group_id,
        p.group_id
    ) AS group_id,
    if(
        p.clip_id = toUUID('00000000-0000-0000-0000-000000000000'),
        c.subgroup_id,
        p.subgroup_id
    ) AS subgroup_id,
    if(
        p.clip_id = toUUID('00000000-0000-0000-0000-000000000000') OR p.take_no = 0,
        c.take_no,
        p.take_no
    ) AS take_no
FROM clips AS c
LEFT JOIN current_placement AS p
    ON p.project_id = c.project_id AND p.clip_id = c.clip_id;

GRANT SELECT ON current_clip_placement TO trimbin_reader;
