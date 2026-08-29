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
