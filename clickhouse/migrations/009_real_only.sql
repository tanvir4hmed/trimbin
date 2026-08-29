-- The real rows, as something you cannot forget to ask for.
--
-- Synthetic rows live at project_id >= 900000 and are excluded from the accuracy
-- and corpus views by that range. Those two were correct. Two other queries were
-- not: the endpoint that publishes why takes are passed over, and the one that
-- publishes what editors say when they overrule us, both read the whole
-- decisions table. That table holds 314,295 generated rows against a dozen real
-- ones, so both figures were essentially reports about a fixture.
--
-- The pattern that failed is the pattern itself. "Remember to add
-- `WHERE project_id < 900000`" is a rule that lives in whoever is writing the
-- query, and it was forgotten twice in the same file. A view cannot be
-- forgotten: a query against real_decisions is scoped whether or not the person
-- writing it was thinking about provenance.
--
-- So: nothing that produces a published number reads the base tables. The base
-- tables stay for the scale demonstration, which is honest about being one.
--
-- One thing to know before adding a column to `clips` or `decisions`:
-- ClickHouse resolves the star below once, when the view is created. These
-- views do not grow a column because the table did, and a query against the new
-- column fails with `Unknown expression identifier` naming the column — which
-- sends whoever reads it to the wrong file. Any migration that adds a column
-- must drop and recreate the views that star that table, in the same file.
-- 014 does this and says so.

CREATE VIEW IF NOT EXISTS real_decisions AS
SELECT * FROM decisions WHERE project_id < 900000;

CREATE VIEW IF NOT EXISTS real_clips AS
SELECT * FROM clips WHERE project_id < 900000;

-- The generated half, named as plainly as the real one.
--
-- Kept, and kept reachable, because the scale demonstration is a real thing to
-- show: this schema answers questions across three hundred thousand clips in
-- milliseconds, and that claim needs three hundred thousand clips. What it must
-- never do is be counted as work anybody did.
CREATE VIEW IF NOT EXISTS synthetic_decisions AS
SELECT * FROM decisions WHERE project_id >= 900000;

CREATE VIEW IF NOT EXISTS synthetic_clips AS
SELECT * FROM clips WHERE project_id >= 900000;
