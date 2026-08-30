-- Who did what.
--
-- The archive records what was decided and by whom, and nothing else. Uploading
-- a shoot day, describing a shot, circling a take, assigning it, marking it
-- approved — all of it happened, none of it was written down, and on a team of
-- three sharing three productions that is the difference between a system of
-- record and a table of verdicts.
--
-- One row per action, never edited. The verb is a closed set for the same reason
-- the finding codes are: free text becomes six spellings of the same thing and
-- then nothing can be counted.

CREATE TABLE IF NOT EXISTS activity
(
    project_id   UInt32,
    group_id     UInt32 DEFAULT 0 COMMENT 'Scene, zero when the action was about the project',
    subgroup_id  UInt32 DEFAULT 0 COMMENT 'Shot, zero when the action was about the scene',

    at           DateTime DEFAULT now(),
    actor        LowCardinality(String),
    actor_role   LowCardinality(String) DEFAULT '',

    verb         LowCardinality(String) COMMENT 'uploaded | compared | chose | confirmed | undid | commented | described | circled | assigned | set_state | planned',
    -- What it was about, in the fewest words that identify it: "12 takes",
    -- "take 4", "scene 12 shot C". Rendered, not parsed.
    detail       String DEFAULT '',
    -- The number the verb acts on, where there is one. A take number for chose,
    -- a clip count for uploaded.
    quantity     UInt32 DEFAULT 0,

    INDEX idx_actor actor TYPE set(64) GRANULARITY 4
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(at)
ORDER BY (project_id, at)
TTL at + INTERVAL 2 YEAR
SETTINGS index_granularity = 8192;


CREATE VIEW IF NOT EXISTS real_activity AS
SELECT * FROM activity WHERE project_id < 900000;

GRANT SELECT ON activity TO trimbin_reader;
GRANT SELECT ON real_activity TO trimbin_reader;
