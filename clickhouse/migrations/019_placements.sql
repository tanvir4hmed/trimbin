-- Where a clip belongs, as an append-only history.
--
-- `clips.group_id` and `clips.subgroup_id` are in the table's ORDER BY key.
-- Moving a misplaced clip therefore cannot be an ordinary update: changing a
-- sorting key means deleting the row and reinserting it, which is a mutation
-- over a partition for a thing a person does by clicking a button.
--
-- So placement stops living on the clip. The clip keeps where it first landed;
-- this table records every proposal and every resolution, and a view resolves
-- the current one. Moving becomes an insert.
--
-- Which is the right shape anyway. "The slate said 12C, the folder said 12B, an
-- editor chose 12C on Tuesday" is three facts about one clip, and the schema
-- that stored only the answer could not tell you which of them you were looking
-- at.

CREATE TABLE IF NOT EXISTS placements
(
    project_id     UInt32,
    clip_id        UUID,

    -- Where this row says the clip belongs.
    group_id       UInt32 COMMENT 'Scene',
    subgroup_id    UInt32 COMMENT 'Shot',
    take_no        UInt16 DEFAULT 0,

    at             DateTime DEFAULT now(),

    -- Who or what decided, and on what evidence.
    source         LowCardinality(String) COMMENT 'slate | folder | timecode | filename | human',
    actor          LowCardinality(String) DEFAULT '' COMMENT 'empty when a machine decided',
    confidence     Float32 DEFAULT 0,

    -- What was declared at upload, when anything was. Kept even after a human
    -- resolves, because "the folder said 12B" is why the question was asked.
    declared_group UInt32 DEFAULT 0,
    declared_shot  UInt32 DEFAULT 0,

    -- What the board actually read, verbatim. The parse can be wrong; the board
    -- is the evidence, and months later this is the only way to tell whether the
    -- slate or the reader was at fault.
    slate_raw      String DEFAULT '',

    -- open   — a disagreement nobody has resolved
    -- settled— agreed, or resolved by a person
    -- ignored— a person said leave it where it is
    state          LowCardinality(String) DEFAULT 'settled',
    detail         String DEFAULT ''
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(at)
-- Newest per clip is the answer, so clip leads and time follows.
ORDER BY (project_id, clip_id, at)
SETTINGS index_granularity = 8192;


-- Where each clip is now: the most recent row per clip.
--
-- A view rather than a materialised column, because the answer is a function of
-- the history and materialising it would put us back where we started — one
-- value that cannot be changed without a mutation.
CREATE VIEW IF NOT EXISTS current_placement AS
SELECT
    project_id,
    clip_id,
    argMax(group_id, at)      AS group_id,
    argMax(subgroup_id, at)   AS subgroup_id,
    argMax(take_no, at)       AS take_no,
    argMax(source, at)        AS source,
    argMax(actor, at)         AS actor,
    argMax(confidence, at)    AS confidence,
    argMax(state, at)         AS state,
    argMax(slate_raw, at)     AS slate_raw,
    argMax(declared_group, at) AS declared_group,
    argMax(declared_shot, at)  AS declared_shot,
    argMax(detail, at)        AS detail,
    max(at)                   AS decided_at
FROM placements
GROUP BY project_id, clip_id;


-- The inbox: clips whose placement nobody has agreed with yet.
CREATE VIEW IF NOT EXISTS placement_inbox AS
SELECT * FROM current_placement WHERE state = 'open';


-- What the file itself said, so an export can stop guessing.
--
-- The frame rate has been measured on every clip since the first week and
-- discarded immediately. Every EDL therefore declares a rate the caller typed,
-- and an EDL cut at 24 for 25fps footage is wrong by a frame a second.
ALTER TABLE clips
    ADD COLUMN IF NOT EXISTS fps Float32 DEFAULT 0
    COMMENT 'From the container. Zero means unmeasured, not 0fps.';

-- For duplicate detection. Two clips with the same content hash are the same
-- file dragged in twice, whatever they are called.
ALTER TABLE clips
    ADD COLUMN IF NOT EXISTS content_hash String DEFAULT ''
    COMMENT 'Of the bytes, not the name. Empty means not computed.';

-- The frame the slate was read from, kept as evidence beside the reading.
ALTER TABLE clips
    ADD COLUMN IF NOT EXISTS slate_uri String DEFAULT '';

-- What the production calls this scene and shot.
--
-- The integers are how the archive sorts and joins; they cannot hold `12A-PU`
-- or `A012C`, and a production that labels a pickup that way means something by
-- it. Stored beside, never instead.
ALTER TABLE clips
    ADD COLUMN IF NOT EXISTS scene_code LowCardinality(String) DEFAULT '';

ALTER TABLE clips
    ADD COLUMN IF NOT EXISTS shot_code LowCardinality(String) DEFAULT '';


CREATE VIEW IF NOT EXISTS real_placements AS
SELECT * FROM placements WHERE project_id < 900000;

GRANT SELECT ON placements TO trimbin_reader;
GRANT SELECT ON current_placement TO trimbin_reader;
GRANT SELECT ON placement_inbox TO trimbin_reader;
GRANT SELECT ON real_placements TO trimbin_reader;
