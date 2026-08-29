-- The read-only user the code has been claiming for weeks.
--
-- `tools/clickhouse_mcp.py` opened with a comment naming a read-only database
-- user as the primary defence and the keyword regex as a convenience. There was
-- no such user. Every connection was the admin one, and a regular expression
-- matching keywords was the only thing between a model-written statement and
-- the production archive.
--
-- A regex over SQL is a filter, not a boundary. A subquery, a comment splicing
-- a keyword, a function whose name contains a forbidden word: all ordinary SQL,
-- none of it what the pattern was written for.
--
-- So this builds what was described. The grant is SELECT and nothing else, and
-- the profile below refuses writes at the server rather than at the prompt —
-- which matters because the caller is a language model reading a question typed
-- by a stranger and a clapperboard a camera was pointed at.

-- A profile that cannot write, whatever statement arrives.
--
-- readonly = 1 refuses every DDL and DML statement and every attempt to change
-- a setting mid-session. Without that last part the flag is one `SET readonly=0`
-- away from meaningless, which is exactly the kind of "protection" this replaces.
CREATE SETTINGS PROFILE IF NOT EXISTS trimbin_reader_profile
SETTINGS
    readonly = 1 CONST,
    -- A runaway query is a cost and a denial of service, not just a slow page.
    max_execution_time = 30 CONST,
    max_result_rows = 1000 CONST,
    max_result_bytes = 20000000 CONST,
    -- Reading is allowed to be slow; reading everything is not.
    max_rows_to_read = 50000000 CONST,
    max_bytes_to_read = 2000000000 CONST;

CREATE ROLE IF NOT EXISTS trimbin_reader
SETTINGS PROFILE trimbin_reader_profile;

-- Only the tables and views a search legitimately touches.
--
-- Deliberately enumerated rather than granted on the database: a future table
-- holding something sensitive should not become readable by an agent because
-- somebody added it, and an explicit list makes that decision visible.
GRANT SELECT ON clips TO trimbin_reader;
GRANT SELECT ON decisions TO trimbin_reader;
GRANT SELECT ON real_clips TO trimbin_reader;
GRANT SELECT ON real_decisions TO trimbin_reader;
GRANT SELECT ON accuracy TO trimbin_reader;
GRANT SELECT ON accuracy_by_project TO trimbin_reader;
GRANT SELECT ON project_corpus TO trimbin_reader;
GRANT SELECT ON corpus TO trimbin_reader;
GRANT SELECT ON review_queue TO trimbin_reader;
GRANT SELECT ON eval_accuracy TO trimbin_reader;

-- Notably absent: supersessions, and anything added later. A grant that has to
-- be written is a grant somebody thought about.
