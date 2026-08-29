-- The word is "shot", everywhere.
--
-- A *shot* is one camera position — 12A the wide, 12B her close-up. A *take* is
-- one attempt at it. That is what a script supervisor means when they draw a
-- vertical line down the page for each setup, and it is what the slate says.
--
-- "Setup" is a real word on set for the same object, and it was the wrong one
-- to build an interface on: nobody says it afterwards. Two vocabularies for one
-- thing is how a screen ends up labelled one way and its data another, and the
-- corpus view was the last place the old one survived.
--
-- Views are replaced rather than altered because a view is a definition, not a
-- table: there is nothing to migrate and nothing that can half-succeed.

DROP VIEW IF EXISTS project_corpus;

CREATE VIEW project_corpus AS
SELECT
    project_id,
    count()                                        AS clips,
    countDistinct(group_id)                        AS scenes,
    -- Renamed from `setups`. Same arithmetic: how many distinct camera
    -- positions this project holds footage for.
    countDistinct((group_id, subgroup_id))         AS shots,
    countIf(status = 'failed')                     AS unusable,
    round(sum(duration_ms) / 3600000, 3)           AS footage_hours,
    max(ingested_at)                               AS last_ingest
FROM real_clips
GROUP BY project_id
ORDER BY project_id;

GRANT SELECT ON project_corpus TO trimbin_reader;
