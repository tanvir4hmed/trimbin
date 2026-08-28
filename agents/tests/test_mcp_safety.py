"""Tests for the read-only guarantee.

Every input this system takes is untrusted: questions typed by people, text on a
clapperboard a camera was pointed at, filenames from a browser. The guarantee
that none of it can reach a write is the single most important property here, so
it is tested at the boundary rather than assumed from a configuration flag.
"""

from __future__ import annotations

import pytest

from trimbin_agents.tools.clickhouse_mcp import (
    ClickHouseMCP,
    UnsafeQuery,
    assert_read_only,
    scope_clause,
    server_env,
)


class TestWritesAreRefused:
    @pytest.mark.parametrize(
        "sql",
        [
            "INSERT INTO decisions VALUES (1)",
            "UPDATE clips SET status = 'failed'",
            "DELETE FROM decisions WHERE 1=1",
            "DROP TABLE clips",
            "TRUNCATE TABLE decisions",
            "ALTER TABLE clips DROP INDEX idx_embedding",
            "CREATE TABLE evil (x Int32)",
            "GRANT ALL ON *.* TO someone",
            "SYSTEM SHUTDOWN",
        ],
    )
    def test_every_write_verb_is_rejected(self, sql: str) -> None:
        with pytest.raises(UnsafeQuery):
            assert_read_only(sql)

    def test_a_write_hidden_behind_a_select_is_rejected(self) -> None:
        """The shape an injected instruction actually takes: something that looks
        like a search with something else riding behind it."""
        with pytest.raises(UnsafeQuery, match="one statement"):
            assert_read_only("SELECT 1; DROP TABLE clips")

    def test_case_does_not_help(self) -> None:
        with pytest.raises(UnsafeQuery):
            assert_read_only("SELECT * FROM clips WHERE 1=1; dRoP TABLE clips")

    def test_a_write_verb_inside_a_select_is_rejected(self) -> None:
        """Conservative on purpose. A false refusal costs one rephrased query;
        a false acceptance costs the archive."""
        with pytest.raises(UnsafeQuery):
            assert_read_only("SELECT * FROM clips WHERE reason LIKE '%DROP TABLE%'")


class TestReadsAreAllowed:
    def test_a_plain_select_passes(self) -> None:
        assert_read_only("SELECT * FROM clips WHERE project_id = 1")

    def test_a_cte_passes(self) -> None:
        """The Archivist's own queries lead with WITH more often than not."""
        assert_read_only(
            "WITH per_shot AS (SELECT 1) SELECT * FROM per_shot"
        )

    def test_a_trailing_semicolon_is_fine(self) -> None:
        assert_read_only("SELECT 1 FROM clips;")

    def test_an_empty_statement_is_not(self) -> None:
        with pytest.raises(UnsafeQuery, match="empty"):
            assert_read_only("   ")


class TestScope:
    def test_a_query_must_name_its_project(self) -> None:
        """Written by us, never asked for in the prompt. A model told to remember
        which project it may read will usually remember; a WHERE clause it never
        sees always does."""
        assert scope_clause(7) == "project_id = 7"

    def test_an_unscoped_query_is_refused(self) -> None:
        with pytest.raises(UnsafeQuery, match="scoped"):
            scope_clause(None)

    def test_the_project_id_cannot_carry_sql(self) -> None:
        """Coerced to an integer, so there is nothing to inject through."""
        with pytest.raises((ValueError, TypeError)):
            scope_clause("1 OR 1=1")  # type: ignore[arg-type]

    async def test_a_query_missing_its_scope_clause_never_runs(self) -> None:
        """A model that forgets the filter must not be able to read another
        project by accident. The check is on the statement itself."""
        with pytest.raises(UnsafeQuery, match="not scoped"):
            await ClickHouseMCP().run_query("SELECT * FROM clips", project_id=7)


class TestLimits:
    def test_an_unbounded_query_is_bounded(self) -> None:
        """A few hundred thousand rows returned in full costs the person waiting
        for the page, not the model that forgot the LIMIT."""
        assert "LIMIT" in ClickHouseMCP._with_limit("SELECT * FROM decisions")

    def test_an_existing_limit_is_respected(self) -> None:
        sql = "SELECT * FROM decisions LIMIT 5"
        assert ClickHouseMCP._with_limit(sql) == sql


class TestServerEnvironment:
    def test_write_access_is_disabled_explicitly(self) -> None:
        """Set rather than left to the default. A default is someone else's
        decision and can change between versions; this one is ours and is
        visible in the diff when it changes."""
        env = server_env()
        assert env["CLICKHOUSE_ALLOW_WRITE_ACCESS"] == "false"
        assert env["CLICKHOUSE_ALLOW_DROP"] == "false"
