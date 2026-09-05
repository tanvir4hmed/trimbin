-- Unassigned is a workflow state, not a fictional Scene 0 / Shot 0.
-- Existing placement history already carries a state column.  `ignored` is
-- the durable state for footage a human deliberately left outside structure;
-- only `settled` rows are canonical shot placement.

CREATE TABLE IF NOT EXISTS clip_lifecycle_events
(
    project_id UInt32,
    clip_id UUID,
    event_id UUID,
    occurred_at DateTime64(3, 'UTC'),
    action LowCardinality(String) COMMENT 'active | deleted | restored',
    actor LowCardinality(String),
    detail String DEFAULT ''
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(occurred_at)
ORDER BY (project_id, clip_id, occurred_at, event_id);

-- `max(occurred_at) AS occurred_at` shadows the column it reads. ClickHouse
-- resolves the name inside `tuple(occurred_at, event_id)` to that alias and
-- refuses the query: an aggregate inside an aggregate (ILLEGAL_AGGREGATION).
-- The ordering tuple is built in a subquery instead, which is the shape
-- `settled_placement` below already uses and the reason it works.
CREATE VIEW IF NOT EXISTS current_clip_lifecycle AS
SELECT
    project_id,
    clip_id,
    argMax(action, lifecycle_order) AS action,
    argMax(actor, lifecycle_order) AS actor,
    argMax(detail, lifecycle_order) AS detail,
    max(occurred_at) AS occurred_at
FROM
(
    SELECT *, tuple(occurred_at, event_id) AS lifecycle_order
    FROM clip_lifecycle_events
)
GROUP BY project_id, clip_id;

DROP VIEW IF EXISTS current_unassigned_clips;
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
    WHERE state = 'settled'
)
GROUP BY project_id, clip_id;

CREATE VIEW current_clip_placement AS
SELECT
    c.project_id AS project_id,
    c.clip_id AS clip_id,
    c.captured_at AS captured_at,
    c.ingested_at AS ingested_at,
    c.uploaded_by AS uploaded_by,
    c.storage_uri AS storage_uri,
    c.proxy_uri AS proxy_uri,
    c.sprite_uri AS sprite_uri,
    c.duration_ms AS duration_ms,
    c.description AS description,
    c.tags AS tags,
    c.exposure_rel AS exposure_rel,
    c.clipping_pct AS clipping_pct,
    c.sharpness_rel AS sharpness_rel,
    c.motion_rel AS motion_rel,
    c.audio_lufs AS audio_lufs,
    c.noise_floor_db AS noise_floor_db,
    c.dropped_frames AS dropped_frames,
    c.slate_confident AS slate_confident,
    c.slate_raw AS slate_raw,
    c.status AS status,
    c.embedding AS embedding,
    c.exposure_raw AS exposure_raw,
    c.sharpness_raw AS sharpness_raw,
    c.motion_raw AS motion_raw,
    c.normalised_at AS normalised_at,
    c.finding_codes AS finding_codes,
    c.finding_starts_s AS finding_starts_s,
    c.finding_ends_s AS finding_ends_s,
    c.camera AS camera,
    c.fps AS fps,
    c.content_hash AS content_hash,
    c.slate_uri AS slate_uri,
    c.scene_code AS scene_code,
    c.shot_code AS shot_code,
    if(s.clip_id = toUUID('00000000-0000-0000-0000-000000000000'), c.group_id, s.group_id) AS group_id,
    if(s.clip_id = toUUID('00000000-0000-0000-0000-000000000000'), c.subgroup_id, s.subgroup_id) AS subgroup_id,
    if(s.clip_id = toUUID('00000000-0000-0000-0000-000000000000') OR s.take_no = 0, c.take_no, s.take_no) AS take_no
FROM clips AS c
LEFT JOIN settled_placement AS s
    ON s.project_id = c.project_id AND s.clip_id = c.clip_id
LEFT JOIN current_placement AS proposed
    ON proposed.project_id = c.project_id AND proposed.clip_id = c.clip_id
LEFT JOIN current_clip_lifecycle AS lifecycle
    ON lifecycle.project_id = c.project_id AND lifecycle.clip_id = c.clip_id
WHERE
    (
        proposed.clip_id = toUUID('00000000-0000-0000-0000-000000000000')
        OR proposed.state = 'settled'
        OR (
            proposed.state = 'open'
            AND s.clip_id != toUUID('00000000-0000-0000-0000-000000000000')
        )
    )
    AND (
        lifecycle.clip_id = toUUID('00000000-0000-0000-0000-000000000000')
        OR lifecycle.action != 'deleted'
    );

CREATE VIEW current_unassigned_clips AS
SELECT
    c.project_id AS project_id,
    c.clip_id AS clip_id,
    c.storage_uri AS storage_uri,
    c.proxy_uri AS proxy_uri,
    c.sprite_uri AS sprite_uri,
    c.slate_uri AS slate_uri,
    c.duration_ms AS duration_ms,
    c.camera AS camera,
    c.fps AS fps,
    c.content_hash AS content_hash,
    c.scene_code AS scene_code,
    c.shot_code AS shot_code,
    p.take_no AS take_no,
    p.actor AS actor,
    p.detail AS detail,
    p.decided_at AS decided_at
FROM clips AS c
INNER JOIN current_placement AS p
    ON p.project_id = c.project_id AND p.clip_id = c.clip_id
LEFT JOIN current_clip_lifecycle AS lifecycle
    ON lifecycle.project_id = c.project_id AND lifecycle.clip_id = c.clip_id
WHERE p.state = 'ignored'
  AND (
      lifecycle.clip_id = toUUID('00000000-0000-0000-0000-000000000000')
      OR lifecycle.action != 'deleted'
  );

GRANT SELECT ON settled_placement TO trimbin_reader;
GRANT SELECT ON current_clip_placement TO trimbin_reader;
GRANT SELECT ON current_unassigned_clips TO trimbin_reader;
GRANT SELECT ON clip_lifecycle_events TO trimbin_reader;
GRANT SELECT ON current_clip_lifecycle TO trimbin_reader;
