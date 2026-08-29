"""Who is on the team, and what that lets them do.

Three roles and no registration form. The company is three editors; everybody
else who arrives is a guest, and a guest is not a spectator.

The distinction that took longest to get right: a guest may change our results.
They can reject a take, disagree with the panel, argue with a finding, leave a
note — on our footage, in our projects. Watching somebody overrule the system
*is* the product, and a demonstration that only lets you look is a video.

What a guest may not do is put footage into our productions. That is the whole
of the restriction, and it is about storage and cost rather than about trust.

In a project a guest created, they are an editor: upload included, with limits
stated up front on the form rather than sprung afterwards.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Role = Literal["lead", "editor", "guest"]

# The company. Named here rather than in a database because a team of three with
# a members table is a team of three plus a members table to keep correct.
#
# The lead is the owner of the productions and the only person who can add
# somebody to one or set a scene aside.
LEAD_EDITOR = "tanvir4hmed@gmail.com"

EDITORS = frozenset({
    "dipon778@gmail.com",
    "mohidewan10@gmail.com",
})


def role_of(email: str | None) -> Role:
    """The role for an address. Anyone not on the roster is a guest.

    Not "unknown", not "none". A guest is a real role with real permissions, and
    calling it an absence is how a guest ends up looking at a page with every
    button disabled.
    """
    if not email:
        return "guest"
    normalised = email.strip().lower()
    if normalised == LEAD_EDITOR:
        return "lead"
    if normalised in EDITORS:
        return "editor"
    return "guest"


def is_staff(email: str | None) -> bool:
    """On the company's roster, either role."""
    return role_of(email) in ("lead", "editor")


@dataclass(frozen=True)
class Limits:
    """What a guest's own project may hold.

    Small enough to bound what a stranger can spend, large enough to see the
    thing work: two scenes' worth of a real shot, compared properly, with the
    reasoning and the archive behind it. Anything tighter would be a screenshot.

    Stated on the New Project form before anyone uploads. A limit discovered
    at the moment of failure reads as a bug; the same limit read beforehand
    reads as a rule.
    """

    projects: int
    scenes: int
    takes_per_shot: int
    clip_seconds: int
    retention_days: int

    def as_dict(self) -> dict:
        return {
            "projects": self.projects,
            "scenes": self.scenes,
            "takes_per_shot": self.takes_per_shot,
            "clip_seconds": self.clip_seconds,
            "retention_days": self.retention_days,
        }


GUEST_LIMITS = Limits(
    projects=2,
    scenes=3,
    takes_per_shot=5,
    clip_seconds=60,
    retention_days=7,
)

# What the company gets in its own productions. Present as a value rather than
# as the absence of one, so a single code path enforces both and there is no
# "if guest" branch that can be forgotten on the third route someone adds.
STAFF_LIMITS = Limits(
    projects=200,
    scenes=500,
    takes_per_shot=64,
    clip_seconds=3600,
    retention_days=0,  # zero means kept
)


def limits_for(email: str | None) -> Limits:
    return STAFF_LIMITS if is_staff(email) else GUEST_LIMITS


def capabilities(email: str | None) -> dict:
    """What to draw, said once, by the side that enforces it.

    The interface asks rather than working it out. A page that decides whether
    to show the upload button by comparing an address against a list is a second
    implementation of this file, and the two will disagree — the failure being a
    button that is drawn and then refused, which is worse than no button.

    These are the answers for *our* projects. Inside a project someone owns,
    they have all of them; that question needs a project id and is answered by
    Principal, not here.
    """
    role = role_of(email)
    return {
        "role": role,
        "signed_in": bool(email),
        "can_read": True,
        "can_comment": bool(email),
        "can_override": bool(email),
        "can_upload_to_team_projects": role in ("lead", "editor"),
        "can_create_own_project": bool(email),
        "can_add_members": role == "lead",
        "can_supersede": role == "lead",
        "limits": limits_for(email).as_dict(),
    }
