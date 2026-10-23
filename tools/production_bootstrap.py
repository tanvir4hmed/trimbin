"""Apply schemas and create the first real owner workspace, preserving existing state."""

import asyncio
import hashlib
import os
import re
from pathlib import Path

import clickhouse_connect
from app.foundation.repository import migrate
from app.services import jobs, projects


def main():
    migrate(os.environ["TRIMBIN_BOOTSTRAP_DATABASE_URL"])
    archive = clickhouse_connect.get_client(
        host="clickhouse",
        port=8123,
        username="default",
        password=os.environ["TRIMBIN_CLICKHOUSE_ADMIN_PASSWORD"],
    )
    archive.command(
        "CREATE TABLE IF NOT EXISTS trimbin_migrations (name String, checksum String) ENGINE=ReplacingMergeTree ORDER BY name"
    )
    access_statements = []
    for path in sorted(Path("/opt/trimbin/clickhouse/migrations").glob("*.sql")):
        text = path.read_text("utf-8")
        digest = hashlib.sha256(text.encode()).hexdigest()
        sql = "\n".join(line.split("--", 1)[0] for line in text.splitlines())
        access_statements.extend(
            statement.strip()
            for statement in sql.split(";")
            if re.match(
                r"^(CREATE (SETTINGS PROFILE|ROLE)|GRANT)\b",
                statement.strip(),
                re.IGNORECASE,
            )
        )
        existing = archive.query(
            "SELECT checksum FROM trimbin_migrations FINAL WHERE name={name:String}",
            parameters={"name": path.name},
        ).result_rows
        if existing:
            if existing[0][0] != digest:
                raise RuntimeError("Applied ClickHouse migration changed: " + path.name)
            continue
        sql = "\n".join(line.split("--", 1)[0] for line in text.splitlines())
        for statement in sql.split(";"):
            if statement.strip():
                archive.command(statement)
        archive.insert(
            "trimbin_migrations",
            [[path.name, digest]],
            column_names=["name", "checksum"],
        )
    # Native database backups do not restore access entities. Reapply the
    # versioned, idempotent role/profile/grant declarations even when the table
    # migration ledger was restored. This never grants an admin fallback.
    for statement in access_statements:
        archive.command(statement)
    for role, variable in (
        ("trimbin_writer", "TRIMBIN_CLICKHOUSE_PASSWORD"),
        ("trimbin_reader", "TRIMBIN_CLICKHOUSE_READER_PASSWORD"),
    ):
        digest = hashlib.sha256(os.environ[variable].encode()).hexdigest()
        archive.command(
            f"CREATE USER IF NOT EXISTS {role} IDENTIFIED WITH sha256_hash BY '{digest}'"
        )
        archive.command(f"ALTER USER {role} IDENTIFIED WITH sha256_hash BY '{digest}'")
    archive.command("GRANT SELECT, INSERT ON default.* TO trimbin_writer")
    archive.command("GRANT trimbin_reader TO trimbin_reader")
    archive.command("ALTER USER trimbin_reader DEFAULT ROLE trimbin_reader")
    archive.close()
    asyncio.run(workspace())
    print("Trimbin schemas and owner workspace ready")


async def workspace():
    owner = os.environ["TRIMBIN_OWNER_EMAIL"].lower()
    found = await projects.for_member(
        owner, states={"active", "archived", "trashed", "deleted"}
    )
    if not found:
        async with jobs.db().connection() as conn:
            row = await (
                await conn.execute("SELECT coalesce(max(id),0) FROM projects")
            ).fetchone()
        await (
            jobs.db()
            .collection("counters")
            .document("project_id")
            .set({"value": row[0]})
        )
        await projects.create("Trimbin", owner)


if __name__ == "__main__":
    main()
