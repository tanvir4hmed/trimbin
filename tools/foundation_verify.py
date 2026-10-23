"""CI-only database lifecycle verification, including a cold backup restoration."""

import os
import subprocess
import sys

import foundation


def main():
    if os.environ.get("CI") != "true":
        raise RuntimeError("Run this destructive disposable-data rehearsal only in CI")
    import psycopg

    environment = {**os.environ, "FOUNDATION_TEST_DSN": foundation.dsn(admin=True)}
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "api/tests/test_foundation_postgres.py",
            "api/tests/test_evidence_postgres.py",
            "api/tests/test_timeline_postgres.py",
            "api/tests/test_exports_postgres.py",
            "api/tests/test_renders_postgres.py",
            "api/tests/test_workflow_postgres.py",
            "-q",
        ],
        cwd=foundation.ROOT,
        env=environment,
        check=True,
    )
    with psycopg.connect(foundation.dsn(admin=True)) as conn:
        before = conn.execute("SELECT count(*) FROM state_versions").fetchone()[0]
        if before < 1:
            raise RuntimeError("No saved revisions to verify")
    foundation.ch(
        "CREATE TABLE IF NOT EXISTS foundation_probe(id UInt64) ENGINE=MergeTree ORDER BY id"
    )
    foundation.ch("INSERT INTO foundation_probe VALUES (1234)")
    foundation.compose("restart")
    foundation.compose("up", "-d", "--wait")
    foundation.check()
    destination = foundation.ROOT / "foundation-backups" / "ci"
    foundation.backup(destination)
    foundation.compose("stop")
    source = foundation.DATA.resolve()
    if source != foundation.ROOT / ".foundation-data":
        raise RuntimeError("Unexpected data location; refusing to move")
    # Preserve the original data rather than deleting it during restore verification.
    source.rename(foundation.ROOT / ".foundation-before-restore")
    source.mkdir()
    foundation.restore(destination)
    foundation.check()
    with psycopg.connect(foundation.dsn(admin=True)) as conn:
        assert (
            conn.execute("SELECT count(*) FROM state_versions").fetchone()[0] == before
        )
    assert foundation.ch("SELECT sum(id) FROM foundation_probe").strip() == "1234"
    # Reapplying migrations must not discard restored data or change the ledger.
    foundation.migrate()
    print("Real DB revisions, leases, restart persistence and cold restore passed.")


if __name__ == "__main__":
    main()
