"""Read the instance-scoped encrypted runtime parameter without logging its value."""

import json
import os
import subprocess
from pathlib import Path

result = subprocess.run(
    [
        "aws",
        "ssm",
        "get-parameter",
        "--region",
        "us-east-1",
        "--name",
        "/trimbin/runtime",
        "--with-decryption",
        "--query",
        "Parameter.Value",
        "--output",
        "text",
    ],
    check=True,
    capture_output=True,
    text=True,
)
configuration = json.loads(result.stdout)
private = Path("/srv/trimbin/private")
private.mkdir(parents=True, exist_ok=True)
private.chmod(0o700)


def write(name, contents, mode=0o600):
    path = private / name
    path.write_text(contents)
    path.chmod(mode)


def env(values):
    # Compose env_file does not interpolate dollar signs inside single quotes.
    if any("\n" in str(v) or "'" in str(v) for v in values.values()):
        raise ValueError("Invalid runtime configuration encoding")
    return "".join(f"{key}='{value}'\n" for key, value in values.items())


runtime = configuration["runtime"]
write("runtime.env", env(runtime))
media = {
    k: v
    for k, v in runtime.items()
    if k
    not in {
        "TRIMBIN_NEBIUS_API_KEY",
        "TRIMBIN_TEAM_PASSES",
        "TRIMBIN_MAINTENANCE_TOKEN",
    }
}
write("media.env", env(media))
write("bootstrap.env", env(configuration["bootstrap"]))
for name, value in configuration["files"].items():
    if name not in {"postgres_admin", "postgres_writer", "clickhouse_admin"}:
        raise ValueError("Unknown secret file")
    write(name, value, 0o444)
base = Path("/srv/trimbin/media")
base.mkdir(parents=True, exist_ok=True)
os.chown(base, 10001, 10001)
for name in ("originals", "staging", "derived", "library", "exports", "model-cache"):
    path = Path("/srv/trimbin/model-cache") if name == "model-cache" else base / name
    previous = Path("/srv/trimbin") / name
    if name != "model-cache" and previous.exists():
        if previous.is_symlink() or path.exists():
            raise RuntimeError("Media layout migration needs operator inspection")
        # Same EBS filesystem; no copying or deleting source data.
        previous.rename(path)
    path.mkdir(parents=True, exist_ok=True)
    os.chown(path, 10001, 10001)
Path("/srv/trimbin/backups/clickhouse").mkdir(parents=True, exist_ok=True)
os.chown("/srv/trimbin/backups/clickhouse", 101, 101)
print("Trimbin private runtime configuration prepared")
