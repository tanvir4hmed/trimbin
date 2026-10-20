"""Local foundation lifecycle. Secrets never enter stdout or Git.

Run with api/.venv's Python for migrate/check. No paid service is contacted.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import tarfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / ".secrets" / "foundation"
DATA = ROOT / ".foundation-data"
COMPOSE = ROOT / "deploy" / "foundation" / "compose.yaml"
POSTGRES_IMAGE = "postgres:17@sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3"


class ClickHouseError(RuntimeError):
    def __init__(self, status: int, code: int):
        self.code = code
        super().__init__(f"ClickHouse request failed (HTTP {status}, code {code})")


def initialize() -> None:
    if PRIVATE.exists():
        raise RuntimeError(
            "Foundation secrets already exist; refusing to overwrite or rotate"
        )
    PRIVATE.mkdir(parents=True, mode=0o700)
    for name in (
        "postgres_admin",
        "postgres_writer",
        "clickhouse_admin",
        "clickhouse_writer",
        "clickhouse_reader",
        "session_secret",
    ):
        path = PRIVATE / name
        path.write_text(secrets.token_hex(32), encoding="utf-8")
        # Compose file secrets are bind mounts; database UIDs must be able to
        # read the mounted file. The enclosing host directory remains 0700.
        path.chmod(
            0o444
            if name in {"postgres_admin", "postgres_writer", "clickhouse_admin"}
            else 0o600
        )
    DATA.mkdir(exist_ok=True)
    env = (
        f"TRIMBIN_FOUNDATION_DATA={DATA.as_posix()}\n"
        f"TRIMBIN_FOUNDATION_SECRETS={PRIVATE.as_posix()}\n"
    )
    (PRIVATE / "compose.env").write_text(env, encoding="utf-8")
    runtime = (ROOT / ".env.example").read_text("utf-8")
    values = {
        "TRIMBIN_DATABASE_URL": dsn(),
        "TRIMBIN_CLICKHOUSE_PASSWORD": secret("clickhouse_writer"),
        "TRIMBIN_CLICKHOUSE_READER_PASSWORD": secret("clickhouse_reader"),
        "TRIMBIN_SESSION_SECRET": secret("session_secret"),
    }
    for key, value in values.items():
        runtime = runtime.replace(f"{key}=\n", f"{key}={value}\n")
    (PRIVATE / "runtime.env").write_text(runtime, encoding="utf-8")
    (PRIVATE / "runtime.env").chmod(0o600)
    print("Generated private foundation configuration; no provider keys required.")


def secret(name: str) -> str:
    return (PRIVATE / name).read_text("utf-8").strip()


def dsn(admin: bool = False) -> str:
    role = "postgres" if admin else "trimbin_writer"
    password = secret("postgres_admin" if admin else "postgres_writer")
    return f"postgresql://{role}:{password}@127.0.0.1:5432/trimbin"


def compose(*args: str, **kwargs):
    return subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(PRIVATE / "compose.env"),
            "-f",
            str(COMPOSE),
            *args,
        ],
        check=True,
        **kwargs,
    )


def ch(sql: str, user: str = "default", password: str | None = None) -> str:
    password = secret("clickhouse_admin") if password is None else password
    auth = base64.b64encode(f"{user}:{password}".encode()).decode()
    req = urllib.request.Request(
        "http://127.0.0.1:8123/?wait_end_of_query=1",
        data=sql.encode(),
        headers={"Authorization": f"Basic {auth}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return response.read().decode()
    except urllib.error.HTTPError as exc:
        # Never echo server query/password material.
        code = re.search(r"Code: (\d+)", exc.read().decode(errors="replace"))
        raise ClickHouseError(exc.code, int(code[1]) if code else 0) from None


def migrate() -> None:
    sys.path[:0] = [str(ROOT / "api"), str(ROOT / "agents")]
    from app.foundation.repository import migrate as migrate_postgres

    migrate_postgres(dsn(admin=True))
    # Retain the existing idempotent evidence migrations, using the same simple
    # statement split as clickhouse/migrate.sh. Credentials are applied separately.
    for path in sorted((ROOT / "clickhouse" / "migrations").glob("*.sql")):
        sql = "\n".join(
            line.split("--", 1)[0] for line in path.read_text("utf-8").splitlines()
        )
        for statement in sql.split(";"):
            if statement.strip():
                ch(statement)
    for role, filename in (
        ("trimbin_writer", "clickhouse_writer"),
        ("trimbin_reader", "clickhouse_reader"),
    ):
        # Hex generated secrets avoid SQL escaping and aren't printed on error.
        digest = hashlib.sha256(secret(filename).encode()).hexdigest()
        ch(
            f"CREATE USER IF NOT EXISTS {role} IDENTIFIED WITH sha256_hash BY '{digest}'"
        )
        ch(f"ALTER USER {role} IDENTIFIED WITH sha256_hash BY '{digest}'")
    ch("GRANT SELECT, INSERT ON default.* TO trimbin_writer")
    ch("GRANT trimbin_reader TO trimbin_reader")
    ch("ALTER USER trimbin_reader DEFAULT ROLE trimbin_reader")
    print("PostgreSQL schema and ClickHouse evidence migrations applied.")


def check() -> None:
    sys.path[:0] = [str(ROOT / "api"), str(ROOT / "agents")]
    import psycopg
    from trimbin_agents.config import Settings

    with psycopg.connect(dsn()) as conn:
        conn.execute("SELECT count(*) FROM state_documents")
        try:
            with conn.transaction():
                conn.execute("CREATE TABLE foundation_forbidden(id integer)")
        except psycopg.errors.InsufficientPrivilege:
            pass
        else:
            raise RuntimeError("Operational writer unexpectedly has DDL rights")
    ch("SELECT count() FROM clips", "trimbin_writer", secret("clickhouse_writer"))
    ch("SELECT count() FROM clips", "trimbin_reader", secret("clickhouse_reader"))
    for user, key in (
        ("trimbin_writer", "clickhouse_writer"),
        ("trimbin_reader", "clickhouse_reader"),
    ):
        try:
            ch(
                "CREATE TABLE foundation_forbidden (id UInt8) ENGINE=Memory",
                user,
                secret(key),
            )
        except ClickHouseError as exc:
            if exc.code not in {164, 497}:
                raise
        else:
            raise RuntimeError(f"{user} unexpectedly has DDL rights")
    try:
        ch(
            "INSERT INTO clips (project_id) VALUES (999999)",
            "trimbin_reader",
            secret("clickhouse_reader"),
        )
    except ClickHouseError as exc:
        if exc.code not in {164, 497}:
            raise
    else:
        raise RuntimeError("Reader unexpectedly has INSERT rights")
    print(
        json.dumps(Settings(_env_file=PRIVATE / "runtime.env").capabilities(), indent=2)
    )
    print("Database connectivity and ClickHouse role isolation passed.")


def backup(destination: Path) -> None:
    destination = destination.resolve()
    if destination.exists() or destination.is_relative_to(DATA.resolve()):
        raise ValueError(
            "Backup must be a new directory outside the database data root"
        )
    destination.mkdir(parents=True, mode=0o700)
    compose("stop")
    try:
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--network=none",
                "--mount",
                f"type=bind,src={DATA.resolve()},dst=/data,readonly",
                "--mount",
                f"type=bind,src={destination},dst=/backup",
                POSTGRES_IMAGE,
                "tar",
                "-cpf",
                "/backup/foundation.tar",
                "-C",
                "/data",
                ".",
            ],
            check=True,
        )
    finally:
        compose("up", "-d", "--wait")
    with (destination / "foundation.tar").open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    (destination / "sha256.txt").write_text(digest, encoding="utf-8")
    print(
        "Cold database backup created. Preserve the matching secret files separately."
    )


def restore(source: Path) -> None:
    source = source.resolve()
    if not (source / "foundation.tar").is_file():
        raise ValueError("Missing foundation.tar")
    with (source / "foundation.tar").open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    if digest != (source / "sha256.txt").read_text("utf-8").strip():
        raise ValueError("Backup checksum mismatch")
    # Recovery uses only trusted operator-created backups. Also reject path/link
    # escapes before handing the archive to the container's tar implementation.
    with tarfile.open(source / "foundation.tar") as archive:
        for member in archive:
            target = (DATA / member.name).resolve()
            if not target.is_relative_to(DATA.resolve()):
                raise ValueError("Backup contains an escaping path")
            if member.issym() or member.islnk():
                linked = (target.parent / member.linkname).resolve()
                if not linked.is_relative_to(DATA.resolve()):
                    raise ValueError("Backup contains an escaping link")
            if not (
                member.isfile() or member.isdir() or member.issym() or member.islnk()
            ):
                raise ValueError("Unsupported archive member")
    if any(DATA.iterdir()):
        raise ValueError(
            "Restore requires an empty data directory; existing data is never deleted"
        )
    compose("stop")
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network=none",
            "--mount",
            f"type=bind,src={source},dst=/backup,readonly",
            "--mount",
            f"type=bind,src={DATA.resolve()},dst=/data",
            POSTGRES_IMAGE,
            "tar",
            "-xpf",
            "/backup/foundation.tar",
            "-C",
            "/data",
        ],
        check=True,
    )
    compose("up", "-d", "--wait")
    print("Backup restored; run check and verify application references before use.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "init",
            "up",
            "stop",
            "migrate",
            "check",
            "backup",
            "restore",
            "config",
        ],
    )
    parser.add_argument("--directory", type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    if args.command == "init":
        initialize()
    elif args.command == "up":
        compose("up", "-d", "--wait")
    elif args.command == "stop":
        compose("stop")
    elif args.command == "config":
        compose("config", "--quiet")
    elif args.command in {"backup", "restore"}:
        if args.directory is None:
            parser.error("--directory is required")
        (backup if args.command == "backup" else restore)(args.directory)
    elif args.command == "migrate":
        migrate()
    else:
        check()


if __name__ == "__main__":
    main()
