"""Create the project records the archive already has rows for.

The dataset was published straight into ClickHouse, which gave us measurements
with no project to hang them from: an editor signing in would have been told,
correctly and unhelpfully, that project 1 does not exist. Membership lives in
Firestore because it changes; measurements live in ClickHouse because they do
not. Both have to exist for either to be reachable.

Ids are not chosen here so much as reserved. Two of them are named in config and
have to keep the meaning config gives them:

    1   the demo scene, public, what a visitor sees without an account
    2   the third dataset scene
    3   the second dataset scene

Id 2 was the visitor sandbox, which no longer exists. Everyone gets the same
application now: a guest signs in, makes their own project, and works it as an
editor here would. The id is kept as an ordinary production rather than reused
for something new, because it already has rows in the archive.

The counter is then set past them, so the next project a person creates does not
land on one of these and inherit its footage.

Idempotent: run it twice and the second run changes nothing.

    python tools/register_projects.py --dry-run
    python tools/register_projects.py
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from app.services import jobs, projects  # noqa: E402

OWNER = "tanvir4hmed@gmail.com"
EDITORS = ["dipon778@gmail.com", "mohidewan10@gmail.com"]

# is_public governs reading without an account, and nothing else. Who may write
# is decided by role, in services/members.py, and who may upload is decided by
# who owns the project — both enforced in the routes. A flag on a document is
# the wrong place to hold the rule that decides who may spend our budget.
PLANNED = [
    {
        "id": 1,
        "name": "Scene 1 - two perspectives (Zenodo DoP C)",
        "is_public": True,
        "note": "CC BY 4.0. The demo project named in config.",
    },
    {
        "id": 2,
        "name": "Scene 3 - two perspectives (Zenodo)",
        "is_public": True,
        "note": "CC BY 4.0. Formerly the visitor sandbox, which no longer exists.",
    },
    {
        "id": 3,
        "name": "Scene 2 - two perspectives (Zenodo DoP F)",
        "is_public": True,
        "note": "CC BY 4.0.",
    },
]


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    db = jobs.db()
    changed = 0

    for spec in PLANNED:
        doc = db.collection(projects.COLLECTION).document(str(spec["id"]))
        snapshot = await doc.get()

        if snapshot.exists:
            existing = snapshot.to_dict() or {}
            missing = [e for e in EDITORS if e not in existing.get("member_emails", [])]
            if not missing:
                print(f"  {spec['id']}  already registered, membership unchanged")
                continue
            print(f"  {spec['id']}  adding {', '.join(missing)}")
            if not args.dry_run:
                for email in missing:
                    await projects.add_member(spec["id"], email)
            changed += 1
            continue

        print(f"  {spec['id']}  create: {spec['name']}")
        print(f"        public={spec['is_public']}  {spec['note']}")
        if not args.dry_run:
            await doc.set({
                "name": spec["name"],
                "owner_email": OWNER,
                "member_emails": EDITORS,
                "is_public": spec["is_public"],
                "created_at": datetime.now(UTC),
            })
        changed += 1

    # Past the reserved block, so the next person to create a project is not
    # handed one that already holds somebody else's footage.
    counter = db.collection("counters").document("project_id")
    snapshot = await counter.get()
    current = (snapshot.to_dict() or {}).get("value", 0) if snapshot.exists else 0
    reserved = max(s["id"] for s in PLANNED)

    if current < reserved:
        print(f"\n  counter {current} -> {reserved}")
        if not args.dry_run:
            await counter.set({"value": reserved})
        changed += 1
    else:
        print(f"\n  counter already at {current}")

    if args.dry_run:
        print(f"\nDry run. {changed} change(s) would be made.")
    else:
        print(f"\n{changed} change(s) written.")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
