-- Which camera shot it.
--
-- Bins in a real cutting room are cut four ways: by scene, by character, by
-- camera, and by shoot day. We had one of those. "Everything on the B camera"
-- and "everything from Tuesday" are ordinary Monday-morning requests, and a
-- tree with a single axis cannot answer either.
--
-- Shoot day was already here — captured_at, from the camera's own metadata, not
-- from when somebody got round to uploading. Camera was not stored at all,
-- despite the slate reader having read it off the board the whole time.
--
-- LowCardinality because a production has two or three of these, not thousands,
-- and the whole column then lives in a dictionary the query never leaves.
ALTER TABLE clips
    ADD COLUMN IF NOT EXISTS camera LowCardinality(String) DEFAULT ''
    COMMENT 'A, B, C — as written on the slate. Empty means single-camera or unread.';


-- The views over clips have to be rebuilt, and this is not optional.
--
-- `real_clips` is `SELECT * FROM clips`, and ClickHouse resolves that star once,
-- at creation. The view therefore carries the column list as it stood in
-- migration 009 and does not grow a `camera` column merely because the table
-- did. The first deploy of this file failed exactly here, with
-- `Unknown expression identifier 'camera'` from a view that was reading a table
-- which plainly has one.
--
-- So: any migration that adds a column to `clips` must also recreate every view
-- that stars it, in the same file. Leaving it to a later migration means a
-- window where the application queries a column the view cannot see, and the
-- error names the column rather than the view — which sends whoever is reading
-- it to the wrong file.
--
-- The definitions below are unchanged from 009. They are repeated rather than
-- referenced because a view is a definition and there is nothing else to point
-- at; DROP then CREATE is idempotent and there is no data to migrate.
DROP VIEW IF EXISTS real_clips;
CREATE VIEW real_clips AS
SELECT * FROM clips WHERE project_id < 900000;

DROP VIEW IF EXISTS synthetic_clips;
CREATE VIEW synthetic_clips AS
SELECT * FROM clips WHERE project_id >= 900000;

GRANT SELECT ON real_clips TO trimbin_reader;


-- What the archive can be asked about a shoot day.
--
-- A view rather than a query in the application, because this is exactly the
-- shape a person asks for out loud and the agent should be able to reach it
-- without composing three joins.
CREATE VIEW IF NOT EXISTS shoot_days AS
SELECT
    project_id,
    toDate(captured_at)                    AS shoot_day,
    camera,
    count()                                AS clips,
    countDistinct(group_id)                AS scenes,
    countDistinct((group_id, subgroup_id)) AS shots,
    round(sum(duration_ms) / 3600000, 3)   AS footage_hours
FROM real_clips
GROUP BY project_id, shoot_day, camera
ORDER BY project_id, shoot_day, camera;


-- The reader may see the new objects too.
--
-- Enumerated, like the first grant, because a table added later should not
-- become readable by an agent merely because it exists. Comments are readable:
-- "what did editors say" is the best question in this archive and refusing it
-- would be refusing the point. Nothing here is writable — the profile is
-- readonly = 1 CONST and that has not changed.
GRANT SELECT ON comments TO trimbin_reader;
GRANT SELECT ON real_comments TO trimbin_reader;
GRANT SELECT ON shoot_days TO trimbin_reader;
