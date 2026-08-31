"""What every endpoint returns, declared.

Forty-two routes returned a bare `dict`. FastAPI publishes those as an empty
object in the OpenAPI schema, so the schema described the paths and nothing
about the answers — and the TypeScript client was therefore hand-written from
memory, mirroring thirty-three shapes that nothing checked.

That is not a theoretical drift. `/projects/{id}` omitted `member_emails` for an
anonymous caller while the hand-written type declared it required, and the
workspace threw a client-side exception for every signed-out visitor. The types
said one thing, the server did another, and both sides compiled.

So the contract lives here, once, and both sides are generated from it: FastAPI
validates responses against these models, and `openapi-typescript` turns the same
models into the types the web app compiles against. A field renamed in Python
now fails the web build.

Models rather than TypedDicts because FastAPI serialises them and validates on
the way out — a route that forgets a field fails here rather than in a browser.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

ShotStatus = Literal[
    "too_few_takes",
    "not_judged",
    "needs_review",
    "differs_from_circle",
    "decided",
    "confirmed",
]

ShotState = Literal["", "needs_review", "in_progress", "approved"]

Role = Literal["lead", "editor", "guest"]


class Model(BaseModel):
    """Base for every response.

    Extra fields are dropped rather than forbidden. A response model is a promise
    about what is present, not a prohibition on a route computing something for
    itself, and forbidding extras turns an additive change into an outage.
    """


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


class Limits(Model):
    projects: int
    scenes: int
    takes_per_shot: int
    clip_seconds: int
    retention_days: int


class Me(Model):
    """Who is asking and what the API will let them do.

    Told rather than inferred. A page that works out whether to draw the upload
    button by comparing an address against a list is a second implementation of
    the permission rules, and the two will disagree.
    """

    email: str | None = None
    signed_in: bool
    role: Role
    can_read: bool
    can_comment: bool
    can_override: bool
    can_curate_team_projects: bool
    can_upload_to_team_projects: bool
    can_create_own_project: bool
    can_add_members: bool
    can_supersede: bool
    limits: Limits
    demo_project_id: int


class AuthOptions(Model):
    google: bool
    password: bool


class Session(Model):
    token: str
    email: str
    name: str
    role: str
    expires_at: int


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


class Project(Model):
    project_id: int
    name: str
    # Always present, emptied rather than omitted for an anonymous reader on a
    # public project. Omitting them is what took the workspace down: the page
    # spreads `member_emails`, and spreading undefined throws.
    #
    # Required rather than defaulted, because a default makes the field optional
    # in the generated schema and pushes the same guard onto every caller for a
    # value the server always sends.
    owner_email: str
    member_emails: list[str]
    is_public: bool
    created_at: str
    you_are_owner: bool
    you_can_upload: bool

    # Present only when the list was asked for with detail.
    scenes: int | None = None
    shots: int | None = None
    takes: int | None = None
    settled: int | None = None
    waiting: int | None = None
    progress_pct: float | None = None


class ProjectList(Model):
    you: str | None = None
    role: str
    limits: Limits
    projects: list[Project]


# ---------------------------------------------------------------------------
# The shot tree
# ---------------------------------------------------------------------------


class ShotNode(Model):
    shot: int
    slug: str
    label: str
    takes: int
    unusable: int
    status: ShotStatus
    state: ShotState
    assignee: str
    circled_take: int
    chosen_take: int
    differs_from_circle: bool
    margin: float
    cameras: list[str]
    shoot_day: str
    open_notes: int


class SceneNode(Model):
    scene: int
    scene_code: str = ""
    shots: list[ShotNode]


class Tree(Model):
    project_id: int
    scenes: list[SceneNode]
    cameras: list[str]
    shoot_days: list[str]
    review_margin: float


# ---------------------------------------------------------------------------
# Takes and verdicts
# ---------------------------------------------------------------------------


class TimeRange(Model):
    start_s: float
    end_s: float


class Finding(Model):
    code: str
    start_s: float
    end_s: float
    detail: str = ""
    severity: str = ""


class Take(Model):
    clip_id: str
    take_no: int
    outcome: str
    score: float
    margin: float
    reason: str
    reason_code: str
    findings: list[Finding]
    usable_from_s: float
    usable_to_s: float
    decided_by: str
    actor: str
    model_id: str
    prompt_version: str
    panel_convened: bool
    decided_at: str | None = None
    proxy_uri: str
    sprite_uri: str
    criteria: dict[str, float]
    safe_ranges: list[TimeRange]
    trim_reasons: list[str]
    duration_s: float
    camera: str = ""
    captured_at: str | None = None
    fps: float = 0.0
    scene_code: str = ""
    shot_code: str = ""


class Verdicts(Model):
    project_id: int
    scene: int
    shot: int
    takes: list[Take]
    recommended: str | None = None
    circled_take: int
    circled_by: str
    differs_from_circle: bool
    assignee: str
    state: ShotState
    rev: int = 0
    selection_archive_state: str = ""


# ---------------------------------------------------------------------------
# What a shot was meant to be
# ---------------------------------------------------------------------------


class Brief(Model):
    scene: int
    shot: int
    slug: str
    heading: str
    action: str
    line: str
    notes: str
    look: str
    circled_take: int
    circled_by: str
    assignee: str
    state: ShotState
    state_by: str
    state_at: str | None = None
    updated_at: str
    updated_by: str
    is_empty: bool
    # The revision the caller must send back to change any of this. See
    # services/revisions.py: a command without it, or with a stale one, is a
    # 409 rather than a silent overwrite of somebody else's edit.
    rev: int = 0
    selected_clip_id: str = ""
    previous_selected_clip_id: str = ""
    selection_event_id: str = ""
    selection_archive_state: str = ""
    note: str | None = None


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------


class Comment(Model):
    comment_id: str
    parent_id: str | None = None
    clip_id: str | None = None
    author: str
    author_role: str
    body: str
    at_s: float
    to_s: float
    whole_take: bool
    created_at: str
    resolved_by: str
    resolved: bool
    is_reply: bool = False


class CommentList(Model):
    project_id: int
    scene: int
    shot: int
    comments: list[Comment]
    open: int


# ---------------------------------------------------------------------------
# The screens
# ---------------------------------------------------------------------------


class QueueItem(Model):
    project_id: int
    project_name: str
    scene: int
    shot: int
    slug: str
    takes: int
    margin: float
    reason: str
    assignee: str
    state: str
    circled_take: int
    chosen_take: int
    open_comments: int


class Activity(Model):
    project_id: int
    project_name: str = ""
    at: str | None = None
    actor: str
    actor_role: str
    verb: str
    detail: str
    quantity: int
    scene: int
    shot: int


class RecentDecision(Model):
    project_id: int
    project_name: str = ""
    scene: int
    shot: int
    take_no: int
    decided_by: str
    actor: str
    reason: str
    decided_at: str | None = None
    margin: float


class RecentNote(Model):
    project_id: int
    project_name: str = ""
    scene: int
    shot: int
    author: str
    body: str
    created_at: str


class Totals(Model):
    waiting: int
    yours: int
    unassigned: int
    projects: int


class ProjectCard(Project):
    members: int = 1


class DashboardScreen(Model):
    you: str | None = None
    role: str
    queue: list[QueueItem]
    queue_total: int
    totals: Totals
    projects: list[ProjectCard]
    recent: list[RecentDecision]
    notes: list[RecentNote]
    activity: list[Activity]
    limits: Limits


class PlannedShot(Model):
    shot: int
    slug: str
    description: str


class PlannedScene(Model):
    scene: int
    heading: str
    shots: list[PlannedShot]


class Plan(Model):
    project_id: int
    scenes: list[PlannedScene]
    next_scene: int


class ProjectScreen(Model):
    """Everything the project workspace draws, in one answer.

    It made four: the tree, the project record, the shot plan, and the caller's
    capabilities. Four round trips for one screen, each with its own loading
    state and its own chance to disagree with the others about who you are.
    """

    project: Project
    tree: Tree
    plan: Plan
    me: Me


class ShotScreen(Model):
    """Everything the shot cockpit draws, in one answer.

    It made three, and the brief arrived after the verdicts — so the shot title
    changed from "Shot 3" to "12B" a moment after the page settled.
    """

    verdicts: Verdicts | None = None
    brief: Brief
    comments: list[Comment]
    open_comments: int


class StringoutEntry(Model):
    scene: int
    shot: int
    slug: str
    clip_id: str
    take_no: int
    start_s: float
    end_s: float
    duration_s: float
    proxy_uri: str
    sprite_uri: str
    reason: str
    decided_by: str
    actor: str
    margin: float
    needs_review: bool
    circled_take: int
    differs_from_circle: bool
    open_comments: int
    fps: float = 0.0
    scene_code: str = ""
    shot_code: str = ""


class Stringout(Model):
    project_id: int
    scene: int
    entries: list[StringoutEntry]
    duration_s: float
    shots: int
    unresolved: int
    disagreements: int
    source_fps: list[float] = []
    export_fps: float = 0.0


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


class Recorded(Model):
    """The answer to an override.

    Says what changed rather than "ok", because the interface tells the editor
    whether they agreed with the panel and that is not knowable from a 201.
    """

    status: str
    agreed_with_panel: bool
    previously_recommended: str | None = None
    now_selected: str
    rev: int = 0
    archive_pending: bool = False


class Undone(Model):
    status: str
    restored: str
    undone_from: str
    rev: int = 0
    archive_pending: bool = False


class Judged(Model):
    status: str
    run_hash: str = ""
    takes: int = 0
    normalised: int = 0
    winner: str | None = None
    margin: float = 0.0
    panel_convened: bool = False
    needs_review: bool = False
    rationale: str = ""
    verdicts_written: int = 0


class UploadGroup(Model):
    scene: int
    shot: int
    takes: int
    unread_slates: int
    mismatches: list[dict]
    status: str


class JobStatus(Model):
    job_id: str
    state: str
    done: bool
    total: int
    completed: int
    failed: int
    failures: list[dict]
    target: dict | None = None
    groups: list[UploadGroup]
    needs_a_look: int
    started_at: str
    finished_at: str | None = None


class PlacementItem(Model):
    clip_id: str
    scene: int
    shot: int
    take_no: int
    source: str
    actor: str
    confidence: float
    state: str
    slate_raw: str
    declared_scene: int
    declared_shot: int
    detail: str
    decided_at: str | None = None
    proxy_uri: str
    sprite_uri: str
    slate_uri: str
    duration_s: float
    camera: str
    filename: str


class PlacementInbox(Model):
    project_id: int
    waiting: list[PlacementItem]
    count: int


class PlacementResolved(Model):
    status: str
    scene: int
    shot: int
    detail: str
