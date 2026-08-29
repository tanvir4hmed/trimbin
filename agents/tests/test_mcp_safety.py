"""Tests for the read-only guarantee.

Every input this system takes is untrusted: questions typed by people, text on a
clapperboard a camera was pointed at, filenames from a browser. The guarantee
that none of it can reach a write is the single most important property here, so
it is tested at the boundary rather than assumed from a configuration flag.
"""

from __future__ import annotations

import pytest

from trimbin_agents.config import settings
from trimbin_agents.tools.clickhouse_mcp import (
    ReaderMissing,
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
    """What the MCP server process is started with.

    The important assertion is the one about *which user*. This file's first
    version tested only the write flags, beside a module comment claiming a
    read-only database user was the primary defence — there was no such user and
    no test asked for one, so the claim went unchallenged for weeks.
    """

    @staticmethod
    def _with_reader(monkeypatch):
        monkeypatch.setattr(settings, "clickhouse_reader_user", "trimbin_reader")
        monkeypatch.setattr(settings, "clickhouse_reader_password", "secret")
        monkeypatch.setattr(settings, "clickhouse_user", "default")
        monkeypatch.setattr(settings, "clickhouse_password", "admin-secret")

    def test_write_access_is_disabled_explicitly(self, monkeypatch) -> None:
        """Set rather than left to the default. A default is someone else's
        decision and can change between versions; this one is ours and is
        visible in the diff when it changes."""
        self._with_reader(monkeypatch)
        env = server_env()
        assert env["CLICKHOUSE_ALLOW_WRITE_ACCESS"] == "false"
        assert env["CLICKHOUSE_ALLOW_DROP"] == "false"

    def test_it_connects_as_the_reader_not_the_admin(self, monkeypatch) -> None:
        """The boundary. Everything else in this module is a courtesy."""
        self._with_reader(monkeypatch)
        env = server_env()
        assert env["CLICKHOUSE_USER"] == "trimbin_reader"
        assert env["CLICKHOUSE_PASSWORD"] == "secret"

    def test_the_admin_password_never_appears(self, monkeypatch) -> None:
        """A read-only user sharing the admin credential is a label, not a
        boundary."""
        self._with_reader(monkeypatch)
        assert "admin-secret" not in server_env().values()

    def test_no_reader_means_no_server(self, monkeypatch) -> None:
        """Refusing is the point. Falling back to the admin connection would
        give a model-written statement write access, silently — which is how the
        previous version of this module came to claim a protection it did not
        have."""
        monkeypatch.setattr(settings, "clickhouse_reader_user", "")
        monkeypatch.setattr(settings, "clickhouse_reader_password", "")

        with pytest.raises(ReaderMissing):
            server_env()

    def test_half_a_credential_is_no_credential(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "clickhouse_reader_user", "trimbin_reader")
        monkeypatch.setattr(settings, "clickhouse_reader_password", "")

        with pytest.raises(ReaderMissing):
            server_env()


class TestAnErrorIsNotAnEmptyResult:
    """The failure that made a working search answer "nothing matched".

    mcp-clickhouse reports a database error as plain text in the same field it
    uses for results. Parsed as "not JSON" and returned as an empty list, that
    becomes an empty archive — and the caller has no way to tell it apart from a
    genuine no-match.

    The cause was a result-size limit on the reader profile, which ClickHouse
    counts *before* LIMIT is applied. A statement ending in LIMIT 20 tripped it,
    and every search came back empty over an archive that had rows.
    """

    @staticmethod
    def _block(text: str):
        class Text:
            def __init__(self, t): self.text = t

        class Result:
            content = [Text(text)]

        return Result()

    def test_a_database_exception_raises(self) -> None:
        from trimbin_agents.tools.clickhouse_mcp import QueryFailed, _rows_from

        message = (
            "Error calling tool 'run_query': Received ClickHouse exception, "
            "code: 396, server response: Code: 396. DB::Exception: Limit for "
            "result exceeded, max rows: 1.00 thousand."
        )
        with pytest.raises(QueryFailed):
            _rows_from(self._block(message))

    def test_the_message_survives_for_the_log(self) -> None:
        """An error that reaches a person as "the search failed" and nothing
        else costs an afternoon."""
        from trimbin_agents.tools.clickhouse_mcp import QueryFailed, _rows_from

        with pytest.raises(QueryFailed, match="TOO_MANY_ROWS"):
            _rows_from(self._block("DB::Exception: TOO_MANY_ROWS_OR_BYTES"))

    def test_real_rows_still_parse(self) -> None:
        import json

        from trimbin_agents.tools.clickhouse_mcp import _rows_from

        rows = [{"clip_id": "abc", "outcome": "selected"}]
        assert _rows_from(self._block(json.dumps(rows))) == rows

    def test_a_genuinely_empty_result_is_still_empty(self) -> None:
        """The distinction only helps if both sides of it work."""
        from trimbin_agents.tools.clickhouse_mcp import _rows_from

        assert _rows_from(self._block("[]")) == []

    def test_text_that_is_neither_is_reported_not_raised(self) -> None:
        """An unfamiliar shape is a bug in this parser, not a failed query. It
        degrades to empty and says so in the log."""
        from trimbin_agents.tools.clickhouse_mcp import _rows_from

        assert _rows_from(self._block("some future format")) == []
