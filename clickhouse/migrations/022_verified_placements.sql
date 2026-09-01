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
    -- Do not use `c.* EXCEPT (...)` in a persisted view. ClickHouse 26.2
    -- preserved the qualifier in the view schema (`c.project_id`) and every
    -- operational query asking for the documented `project_id` failed. A
    -- canonical relation is a contract, so spell the contract out.
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
WHERE NOT (
    proposed.state = 'open'
    AND s.clip_id = toUUID('00000000-0000-0000-0000-000000000000')
);

GRANT SELECT ON settled_placement TO trimbin_reader;
GRANT SELECT ON current_clip_placement TO trimbin_reader;
