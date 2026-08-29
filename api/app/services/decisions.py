"""Writing verdicts to the archive.

Every take of every shot gets a row, not only the winner. A shot where six takes
were rejected and one chosen is six explanations and one selection, and the six
are the part an editor actually argues with — "why not that one?" is the
question this table exists to answer, months later, when nobody remembers.

Losers from an early bracket round keep the verdict from the round they lost in.
Dropping them would leave gaps exactly where the question gets asked.

Nothing here is written by a model. The Analyst produces judgement and language;
the shape, the provenance and the idempotency key are attached here, where a
signature decides what is legal.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from uuid import UUID

from .analytics import client

log = logging.getLogger(__name__)

_COLUMNS = [
    "project_id", "group_id", "subgroup_id", "clip_id", "decided_at",
    "outcome", "score", "margin",
    "reason", "reason_code",
    "finding_codes", "finding_starts_s", "finding_ends_s", "finding_severities",
    "decided_by", "actor_id",
    "model_id", "prompt_version", "bracket_round", "panel_convened", "run_hash",
    "in_point_s", "out_point_s",
    "criterion_names", "criterion_scores",
    "safe_starts_s", "safe_ends_s", "trim_reasons",
]


def run_hash(project_id: int, group_id: int, subgroup_id: int, clip_ids: list[UUID]) -> str:
    """An idempotency key for one analysis of one setup.

    A batch that fails halfway is re-run, and without this the second attempt
    appends a second full set of verdicts. The accuracy figures count decisions,
    so duplicates would not merely clutter the table — they would move the
    number this system publishes about itself.

    Derived from what was analysed rather than when, so a genuine re-analysis
    after a take is added produces a different key and is correctly kept as a
    separate event.
    """
    material = f"{project_id}/{group_id}/{subgroup_id}/" + ",".join(
        sorted(str(c) for c in clip_ids)
    )
    return hashlib.sha256(material.encode()).hexdigest()[:32]


async def already_recorded(project_id: int, key: str) -> bool:
    ch = await client()
    result = await ch.query(
        "SELECT count() FROM decisions WHERE project_id = {p:UInt32} AND run_hash = {h:String}",
        parameters={"p": project_id, "h": key},
    )
    return bool(result.result_rows and result.result_rows[0][0])


async def record(
    project_id: int,
    group_id: int,
    subgroup_id: int,
    verdicts: list[dict],
    key: str,
    model_id: str,
    prompt_version: str,
    bracket_round: int = 0,
    panel_convened: bool = False,
    actor_id: str = "analyst",
    decided_by: str = "agent",
) -> int:
    """Write one row per take.

    Each verdict is a plain dict rather than a contract type, because this
    service is also how a human decision is recorded — an editor overriding the
    panel writes through here with decided_by='human' — and a human decision has
    no AnalysisResult behind it.
    """
    if not verdicts:
        return 0

    now = datetime.now(UTC)
    rows = []
    for v in verdicts:
        codes, starts, ends, severities = _findings(v.get("findings", []))
        rows.append([
            project_id, group_id, subgroup_id, UUID(str(v["clip_id"])), now,
            v["outcome"], float(v.get("score", 0.0)), float(v.get("margin", 0.0)),
            v.get("reason", "")[:400], _code_value(v.get("reason_code", "")),
            codes, starts, ends, severities,
            decided_by, actor_id,
            model_id, prompt_version, bracket_round, 1 if panel_convened else 0, key,
            float(v.get("in_point_s", 0.0)), float(v.get("out_point_s", 0.0)),
            list(v.get("criterion_names", [])), list(v.get("criterion_scores", [])),
            list(v.get("safe_starts_s", [])), list(v.get("safe_ends_s", [])),
            list(v.get("trim_reasons", [])),
        ])

    await (await client()).insert("decisions", rows, column_names=_COLUMNS)
    log.info(
        "recorded %d verdicts for project %d scene %d setup %d (%s)",
        len(rows), project_id, group_id, subgroup_id,
        "panel" if panel_convened else "measurements",
    )
    return len(rows)


def _findings(
    findings: list,
) -> tuple[list[str], list[float], list[float], list[str]]:
    """Flatten findings into four parallel arrays.

    Parallel arrays rather than a nested type because ClickHouse reads columns,
    and the common query — every clip carrying a given code — touches one array
    instead of unpacking a struct per row.

    A finding with no span applies to the whole take, and is written as 0-0
    rather than dropped. "Underexposed throughout" is a real finding; losing it
    because it has no timecode would silently discard the worst problems, which
    are exactly the ones that last the whole clip.
    """
    codes: list[str] = []
    starts: list[float] = []
    ends: list[float] = []
    severities: list[str] = []

    for f in findings:
        code = _attr(f, "code")
        if not code:
            continue

        # .value, not str(). From Python 3.11 a `str, Enum` member stringifies
        # to "FindingCode.CONTINUITY_BLOCKING" rather than to its value, so the
        # archive filled with class names — which match no query, and none of
        # the scoring tables either. The scores came out perfect for every take
        # because nothing recognised anything.
        codes.append(_code_value(code))

        # Two shapes arrive here and only one was handled.
        #
        # A contract Finding nests its span in `where`. Everything upstream of
        # this — review._merge_findings, an override posted as JSON — passes it
        # flat, as start_s and end_s. Reading only `where` found nothing on the
        # flat shape and wrote 0.0, so *every* timecode in the decisions table
        # has been zero since this was written.
        #
        # It cost a long detour: the prompt was rewritten to demand timecodes,
        # the schema was made to require them, and the model was in fact
        # supplying them the whole time. Nothing was wrong upstream. The rows
        # were being flattened on the way in.
        start, end = _span(f)
        starts.append(round(start, 2))
        ends.append(round(end, 2))

        # How bad the panel said it was, kept rather than reconstructed later.
        #
        # This was dropped for months and nothing noticed, because the one
        # screen that read findings back coloured them all alike. It surfaced
        # the moment they became timeline markers: the exporter had to say which
        # of a hundred notes an editor should stop for, had no severity, and
        # guessed from the code's name. `continuity.blocking` is a note about
        # where an actor stands, and every one of them arrived in Resolve as a
        # red marker meaning the take was unusable.
        #
        # Absent stays absent. A default of "attention" here would be the same
        # guess one layer down, and a level nobody chose is worth less than an
        # absence said out loud.
        severities.append(_code_value(_attr(f, "severity") or ""))

    return codes, starts, ends, severities


def _span(finding) -> tuple[float, float]:
    """The finding's timecodes, whichever shape it arrived in.

    Nested under `where` on a contract object; flat on a dict. Both are
    legitimate — one comes from an agent, the other from a route — and a writer
    that understands only one silently drops the other's data.
    """
    where = _attr(finding, "where")
    if where is not None:
        return (
            float(_attr(where, "start_s") or 0.0),
            float(_attr(where, "end_s") or 0.0),
        )
    return (
        float(_attr(finding, "start_s") or 0.0),
        float(_attr(finding, "end_s") or 0.0),
    )


def _code_value(code) -> str:
    """The string an enum member stands for, whatever Python does to str().

    Works for a bare string too, because a human override arrives as JSON and
    has no enum to unwrap.
    """
    return str(getattr(code, "value", code))


def _attr(obj, name: str):
    """Read a field from either a contract object or the dict form of one.

    Both arrive here: the Analyst hands over pydantic models, and a human
    override comes in as JSON from a route.
    """
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)
