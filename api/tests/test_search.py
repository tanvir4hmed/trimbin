"""Tests for turning a question into a query.

The model does not write SQL here. It fills in a fixed shape, and these test
that the shape is built correctly from what it fills in — because the failure
mode of the alternative is a model reaching rows it should not, and the failure
mode of this one is quieter: a filter silently dropped, so a question about
scene 12 answers about everything.

The plan said the Archivist would query through MCP. The wrapper for that exists
and its safety check names a read-only database user as the primary defence;
there is no such user, the connection is the admin one, and the only thing
between a model and the archive was a regular expression matching keywords. A
regex over SQL is a filter, not a boundary.
"""

from __future__ import annotations

import inspect
import re

import pytest

from app.services import search


def sql_for(plan: dict, embedding: list[float] | None = None) -> tuple[str, dict]:
    """Build the statement without running it.

    Reaches into run() rather than duplicating its logic, because a test that
    restates the query is a test of the restatement.
    """
    captured: dict = {}

    class FakeResult:
        column_names: list[str] = []
        result_rows: list[list] = []

    class FakeClient:
        async def query(self, sql, parameters=None):
            captured["sql"] = sql
            captured["params"] = parameters or {}
            return FakeResult()

    import asyncio

    async def go():
        original = search.client

        async def fake_client():
            return FakeClient()

        search.client = fake_client  # type: ignore[assignment]
        try:
            await search.run(7, plan, embedding)
        finally:
            search.client = original  # type: ignore[assignment]

    asyncio.run(go())
    return captured["sql"], captured["params"]


class TestEveryQueryIsScopedToOneProject:
    """The single condition that must never be missing.

    Everything else being wrong produces a bad answer. This being wrong produces
    somebody else's footage.
    """

    def test_the_project_is_always_in_the_where_clause(self) -> None:
        sql, params = sql_for({})
        assert "d.project_id = {project_id:UInt32}" in sql
        assert params["project_id"] == 7

    def test_an_empty_plan_still_scopes(self) -> None:
        """ "Show me everything" means everything in *this* project."""
        sql, params = sql_for({"text": "", "scene": None, "outcome": None})
        assert "project_id" in sql
        assert params["project_id"] == 7

    def test_the_project_is_a_parameter_not_a_string(self) -> None:
        """Interpolated, it would be the one place a caller could reach past
        their own project."""
        sql, _ = sql_for({})
        assert "= 7" not in sql


class TestFiltersReachTheQuery:
    def test_a_scene_narrows(self) -> None:
        sql, params = sql_for({"scene": 12})
        assert "c.group_id = {scene:UInt32}" in sql
        assert params["scene"] == 12

    def test_scene_zero_is_a_real_scene(self) -> None:
        """Ungrouped clips sit in scene zero. A truthiness check would drop the
        filter and answer about the whole project instead."""
        sql, params = sql_for({"scene": 0})
        assert "c.group_id" in sql
        assert params["scene"] == 0

    def test_an_outcome_narrows(self) -> None:
        sql, params = sql_for({"outcome": "not_selected"})
        assert "d.outcome = {outcome:String}" in sql
        assert params["outcome"] == "not_selected"

    def test_who_decided_narrows(self) -> None:
        sql, params = sql_for({"decided_by": "human"})
        assert "d.decided_by" in sql
        assert params["decided_by"] == "human"

    def test_a_finding_narrows(self) -> None:
        sql, params = sql_for({"finding": "continuity.prop"})
        assert "has(d.finding_codes" in sql
        assert params["finding"] == "continuity.prop"

    def test_a_finding_enum_reaches_the_query_as_its_value(self) -> None:
        """From Python 3.11 a str-Enum stringifies to its class name, which
        matches nothing in the archive — the same trap that made every criterion
        score come out perfect."""
        from trimbin_agents.contracts.base import FindingCode

        _, params = sql_for({"finding": FindingCode.CONTINUITY_PROP})
        assert params["finding"] == "continuity.prop"


class TestTextSearch:
    def test_words_are_a_parameter(self) -> None:
        sql, params = sql_for({"text": "boom"})
        assert "{text:String}" in sql
        assert params["text"] == "boom"

    def test_a_quote_cannot_end_the_string(self) -> None:
        """Parameterised, so this is a search for an odd word rather than an
        injection. Tested because "it is parameterised" is a claim worth
        holding."""
        _, params = sql_for({"text": "' OR 1=1 --"})
        assert params["text"] == "' OR 1=1 --"

    def test_it_looks_where_people_actually_wrote(self) -> None:
        sql, _ = sql_for({"text": "boom"})
        for column in ("d.reason", "c.description", "c.slate_raw", "d.finding_codes"):
            assert column in sql


class TestSemanticSearch:
    def test_an_embedding_adds_a_distance_term(self) -> None:
        sql, params = sql_for({"semantic": "a wide shot"}, [0.1] * 768)
        assert "cosineDistance" in sql
        assert len(params["vec"]) == 768

    def test_without_one_there_is_no_distance_term(self) -> None:
        sql, _ = sql_for({"semantic": "a wide shot"}, None)
        assert "cosineDistance" not in sql

    def test_it_is_weighted_below_a_word_match(self) -> None:
        """Within one production every clip resembles every other — the
        misplacement eval measured 0.91 to 0.98 across the board. Unweighted,
        this would rank everything near the top and drown the rows that matched
        something a person actually wrote."""
        assert search.SEMANTIC_WEIGHT < search.TEXT_WEIGHT


class TestResultSize:
    def test_a_limit_is_always_applied(self) -> None:
        sql, params = sql_for({})
        assert "LIMIT {limit:UInt16}" in sql
        assert params["limit"] > 0

    def test_an_enormous_limit_is_capped(self) -> None:
        """Beyond a point the result is a listing, not an answer, and the cost
        lands on whoever is waiting for the page."""
        _, params = sql_for({"limit": 100_000})
        assert params["limit"] == search.HARD_LIMIT

    def test_one_row_per_clip(self) -> None:
        """A clip judged by the panel and then overruled by an editor has two
        decisions. Both are kept; the search returns the current one."""
        sql, _ = sql_for({})
        assert "LIMIT 1 BY d.clip_id" in sql


class TestWideningIsOfferedNotSubstituted:
    def test_it_drops_one_filter_at_a_time(self) -> None:
        """Dropping everything at once returns the whole project, which answers
        a question nobody asked."""
        source = inspect.getsource(search.widen)
        assert "return await run" in source

    def test_text_is_relaxed_before_structure(self) -> None:
        """An editor searching for a word they remember writing is often
        remembering it differently. A scene number they gave is rarely wrong."""
        order = inspect.getsource(search.widen)
        assert order.index('"text"') < order.index('"setup"')


class TestTheOutcomeComesFromTheRows:
    """Not from the model. QueryResult refuses to hold `found` with no matches,
    so letting a model name the outcome turns a hallucination into a validation
    error at best and a wrong answer at worst."""

    def test_no_rows_is_no_match(self) -> None:
        from trimbin_agents.archivist.agent import outcome_for
        from trimbin_agents.contracts.query import Outcome

        assert outcome_for([], widened=False) is Outcome.NO_MATCH

    def test_no_rows_after_widening_is_still_no_match(self) -> None:
        from trimbin_agents.archivist.agent import outcome_for
        from trimbin_agents.contracts.query import Outcome

        assert outcome_for([], widened=True) is Outcome.NO_MATCH

    def test_widened_rows_are_labelled_as_such(self) -> None:
        from trimbin_agents.archivist.agent import outcome_for
        from trimbin_agents.contracts.query import Outcome

        assert outcome_for([object()], widened=True) is Outcome.WIDENED


class TestThePlanTheModelFillsIn:
    def test_an_invented_outcome_is_refused(self) -> None:
        from pydantic import ValidationError
        from trimbin_agents.contracts.search import SearchPlan

        with pytest.raises(ValidationError):
            SearchPlan(outcome="rejected")

    def test_an_invented_decider_is_refused(self) -> None:
        from pydantic import ValidationError
        from trimbin_agents.contracts.search import SearchPlan

        with pytest.raises(ValidationError):
            SearchPlan(decided_by="the director")

    def test_an_invented_finding_code_is_refused(self) -> None:
        """The taxonomy is closed everywhere else; a search that accepted a code
        outside it would return nothing and look like an empty archive."""
        from pydantic import ValidationError
        from trimbin_agents.contracts.search import SearchPlan

        with pytest.raises(ValidationError):
            SearchPlan(finding="hair.style_mismatch")

    def test_an_empty_plan_knows_it_is_empty(self) -> None:
        """ "Show me everything" and "I could not turn that into a search"
        produce the same object and mean different things to the person
        waiting."""
        from trimbin_agents.contracts.search import SearchPlan

        assert SearchPlan().is_empty()
        assert not SearchPlan(scene=1).is_empty()


class TestTheColumnNamesMatchTheSelect:
    """The names are supplied by us, so they have to be right.

    mcp-clickhouse returns positional rows with no usable header, so the caller
    zips its own names onto them. That is correct — the caller wrote the SELECT
    — but it means a mismatch mislabels every column silently rather than
    failing, which is worse than an error.

    Reading them out of the response instead is what shipped first: the parser
    looked for objects, found lists, returned empty, and six rows became
    "nothing matched".
    """

    @staticmethod
    def _aliases(sql: str) -> list[str]:
        """The AS names in the SELECT, in order."""
        select = sql[sql.index("SELECT") : sql.index("FROM decisions")]
        return re.findall(r"\bAS\s+(\w+)", select)

    def test_every_selected_column_is_named(self) -> None:
        sql, _ = sql_for({})
        assert self._aliases(sql) == search._COLUMNS

    def test_the_count_matches(self) -> None:
        sql, _ = sql_for({})
        assert len(self._aliases(sql)) == len(search._COLUMNS)

    def test_it_holds_with_every_filter_on(self) -> None:
        """The relevance expression changes shape when text or an embedding is
        present. The alias must not move with it."""
        sql, _ = sql_for(
            {"text": "boom", "scene": 1, "outcome": "not_selected", "semantic": "wide"},
            [0.1] * 768,
        )
        assert self._aliases(sql) == search._COLUMNS

    def test_clip_id_comes_first(self) -> None:
        """Everything downstream keys on it. If the order drifts, this is the
        one that turns a result into somebody else's take."""
        assert search._COLUMNS[0] == "clip_id"
