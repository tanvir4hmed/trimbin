-- Clips: one row per piece of footage that ever entered the system.
--
-- Ordering follows ClickHouse's own guidance — filter columns first, lowest
-- cardinality leading, time last. Almost every query here is scoped to a project
-- and then narrowed to a scene and a shot, which is exactly this order, so the
-- index skips whole granules rather than scanning them.
--
-- No Nullable columns anywhere. Defaults carry "not measured" instead, because
-- Nullable costs a second file per column and every read pays for it.

CREATE TABLE IF NOT EXISTS clips
(
    -- identity ------------------------------------------------------------
    project_id       UInt32,
    group_id         UInt32 COMMENT 'Scene, in film vocabulary',
    subgroup_id      UInt32 COMMENT 'Shot',
    take_no          UInt16,
    clip_id          UUID,

    -- provenance ----------------------------------------------------------
    captured_at      DateTime COMMENT 'From camera metadata, not upload time',
    ingested_at      DateTime DEFAULT now(),
    uploaded_by      LowCardinality(String) DEFAULT '',

    -- storage: pointers only. ClickHouse never holds media ------------------
    storage_uri      String COMMENT 'Original in Cloud Storage',
    proxy_uri        String DEFAULT '' COMMENT 'HLS manifest for playback',
    sprite_uri       String DEFAULT '' COMMENT 'Thumbnail sheet for scrubbing',

    -- what it is ----------------------------------------------------------
    duration_ms      UInt32,
    description      String DEFAULT '' COMMENT 'Plain-English summary from the model',
    tags             Array(LowCardinality(String)) DEFAULT [],

    -- measurements, from ffmpeg in the proxy pass ---------------------------
    -- Relative values are ratios against the median of the same shot. Absolute
    -- thresholds would condemn a deliberately handheld scene wholesale; the only
    -- question worth asking is whether a take is unlike its siblings.
    exposure_rel     Float32 DEFAULT 1.0,
    clipping_pct     Float32 DEFAULT 0,
    sharpness_rel    Float32 DEFAULT 1.0,
    motion_rel       Float32 DEFAULT 1.0,
    audio_lufs       Float32 DEFAULT 0,
    noise_floor_db   Float32 DEFAULT 0,
    dropped_frames   UInt16 DEFAULT 0,

    -- grouping confidence --------------------------------------------------
    slate_confident  UInt8 DEFAULT 0 COMMENT '1 = read from a slate, 0 = inferred',
    slate_raw        String DEFAULT '' COMMENT 'Exactly what was on the board, before parsing',

    -- lifecycle ------------------------------------------------------------
    status           Enum8('active' = 1, 'superseded' = 2, 'failed' = 3) DEFAULT 'active',

    -- similarity -----------------------------------------------------------
    -- Native multimodal embedding of the footage itself, not of its written
    -- description. Whether a clip belongs to this scene is a question about how
    -- it looks, and routing that through prose loses most of the signal.
    -- The index fixes the dimension, so the default has to match it rather than
    -- being empty: a clip that has not been embedded yet still occupies a row.
    -- A zero vector is degenerate in the index and simply never matches, which
    -- is the correct behaviour for "not embedded".
    embedding        Array(Float32) DEFAULT arrayWithConstant(768, toFloat32(0)),

    INDEX idx_embedding embedding TYPE vector_similarity('hnsw', 'cosineDistance', 768) GRANULARITY 1,
    INDEX idx_description description TYPE text(tokenizer = 'splitByNonAlpha') GRANULARITY 1,
    INDEX idx_duration duration_ms TYPE minmax GRANULARITY 4
)
ENGINE = MergeTree
-- Partition by month, not by project. Partitions exist for data manipulation —
-- dropping an expired month in one operation — not for query speed; the ORDER BY
-- key already makes project-scoped reads fast. Partitioning per project would
-- create one partition per production and degrade everything, which is a common
-- enough mistake that ClickHouse refuses the insert outright.
PARTITION BY toYYYYMM(captured_at)
ORDER BY (project_id, group_id, subgroup_id, take_no, captured_at)
SETTINGS index_granularity = 8192;
