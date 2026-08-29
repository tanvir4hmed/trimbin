-- What a person said about a take, anchored to a second.
--
-- The archive already holds what the panel measured and what an editor decided.
-- It has never held what anyone *said* — and in every tool editors already use,
-- the timecoded comment is the thing they spend their day in. Frame.io's whole
-- interaction is: pause, type, the note sticks to that frame.
--
-- ClickHouse rather than Firestore, unlike the shot brief. A brief is a thing
-- somebody edits four times and only the current text matters. A comment is an
-- event: it happened, at a time, by a person, about a frame, and it stays true
-- afterwards. It is also the half of the archive that can be asked questions —
-- "what do editors actually say when they reject a take for continuity" is
-- answerable from this table and from nowhere else.
--
-- Resolution is a second row, not an UPDATE. Same reason overrides are: the
-- disagreement is the data.

CREATE TABLE IF NOT EXISTS comments
(
    project_id     UInt32,
    group_id       UInt32 COMMENT 'Scene',
    subgroup_id    UInt32 COMMENT 'Shot',
    clip_id        UUID COMMENT 'The take. Zero uuid means the comment is about the shot.',

    comment_id     UUID,
    -- Zero means a reply to nothing: a top-level comment. A thread is one level
    -- deep on purpose — an editing note that needs a nested argument needs a
    -- phone call.
    parent_id      UUID DEFAULT toUUID('00000000-0000-0000-0000-000000000000'),

    author         LowCardinality(String),
    author_role    LowCardinality(String) DEFAULT '' COMMENT 'lead, editor, guest — as at the time',
    body           String,

    -- Where in the take. Both zero means the comment is about the whole thing,
    -- which is a normal thing to say and not a missing value.
    at_s           Float32 DEFAULT 0,
    to_s           Float32 DEFAULT 0,

    created_at     DateTime DEFAULT now(),
    -- An empty string is open. Resolution names who closed it, because "someone
    -- marked this done" is not the same information as "Maya marked this done".
    resolved_by    LowCardinality(String) DEFAULT '',
    resolved_at    DateTime DEFAULT toDateTime(0),

    INDEX idx_body body TYPE text(tokenizer = 'splitByNonAlpha') GRANULARITY 1
)
ENGINE = ReplacingMergeTree(created_at)
PARTITION BY toYYYYMM(created_at)
-- Same leading key as clips and decisions, so a shot's comments sit beside its
-- verdicts on disk and the join that draws one screen reads one range.
ORDER BY (project_id, group_id, subgroup_id, comment_id)
SETTINGS index_granularity = 8192;


-- Comments on real work only, for the same reason real_decisions exists: a
-- published figure must never be able to read a generated row by accident.
CREATE VIEW IF NOT EXISTS real_comments AS
SELECT * FROM comments WHERE project_id < 900000;
