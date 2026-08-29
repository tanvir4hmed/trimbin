-- How bad each finding is, kept rather than guessed.
--
-- The panel has always produced a severity per finding — note, attention,
-- blocking — and the writer dropped it. Only the code, the start and the end
-- reached the table.
--
-- That was survivable while findings were only ever read back into the same
-- screen, which colours them all the same. It stopped being survivable when
-- they became timeline markers: a marker file has to say which of a hundred
-- notes an editor should stop for, and with no severity the exporter invented
-- one from the code's name.
--
-- It invented it wrongly, in the way these things always go wrong — plausibly.
-- The rule was "a code ending in .blocking is blocking", and `continuity.blocking`
-- is a note about where an actor stands. Every one of those arrived in Resolve
-- as a red marker meaning the take cannot be used.
--
-- So the severity is stored. Rows written before this carry an empty array, and
-- the readers treat that as "not recorded" rather than as a level — an absence
-- said out loud is worth more than a level nobody chose.

ALTER TABLE decisions
    ADD COLUMN IF NOT EXISTS finding_severities Array(LowCardinality(String)) DEFAULT []
    COMMENT 'note | attention | blocking, parallel to finding_codes. Empty on rows written before this existed.';


-- The views over decisions star the table, and ClickHouse resolved that star
-- when they were created. They do not grow a column because the table did.
-- See the note in 009 and the same rebuild in 014.
DROP VIEW IF EXISTS real_decisions;
CREATE VIEW real_decisions AS
SELECT * FROM decisions WHERE project_id < 900000;

DROP VIEW IF EXISTS synthetic_decisions;
CREATE VIEW synthetic_decisions AS
SELECT * FROM decisions WHERE project_id >= 900000;

GRANT SELECT ON real_decisions TO trimbin_reader;
