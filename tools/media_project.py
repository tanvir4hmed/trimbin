"""Operator-only portable project bootstrap; never a browser authorization bypass."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from app.config import Settings
from app.media.store import MediaStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--project", type=int, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--role", choices=["owner", "editor", "viewer"], required=True)
    args = parser.parse_args()
    if args.project < 1 or "@" not in args.email:
        parser.error("Positive project ID and account email required")
    config = Settings(_env_file=args.env_file)
    with MediaStore(config.database_url).connection() as conn:
        conn.execute(
            "INSERT INTO projects(id,name) VALUES (%s,%s) ON CONFLICT DO NOTHING",
            (args.project, args.name),
        )
        conn.execute(
            """INSERT INTO project_members(project_id,email,role) VALUES (%s,%s,%s)
               ON CONFLICT(project_id,email) DO UPDATE SET role=excluded.role""",
            (args.project, args.email.lower(), args.role),
        )
    print("Project membership saved. No provider call or cloud resource created.")


if __name__ == "__main__":
    main()
