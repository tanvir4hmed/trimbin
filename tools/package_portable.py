"""Package an immutable Git commit, including frontend and license, without local files."""

import argparse
import gzip
import hashlib
import json
import subprocess
import tarfile
from io import BytesIO
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
TOP = {
    "api",
    "agents",
    "web",
    "deploy",
    "clickhouse",
    "tools",
    "docs",
    "config",
    "eval",
    "infra",
    ".github",
}
ROOT_FILES = {
    "LICENSE",
    "AGENTS.md",
    "README.md",
    "SECURITY.md",
    ".dockerignore",
    ".env.example",
    ".gitignore",
    ".gitattributes",
}
EXTENSIONS = {
    ".py",
    ".sql",
    ".json",
    ".toml",
    ".lock",
    ".md",
    ".yaml",
    ".yml",
    ".sh",
    ".ts",
    ".tsx",
    ".js",
    ".mjs",
    ".cjs",
    ".css",
    ".svg",
    ".conf",
    ".txt",
    ".tf",
    ".hcl",
}


def allowed(name: str) -> bool:
    path = PurePosixPath(name)
    if not name or path.is_absolute() or ".." in path.parts:
        return False
    if name in ROOT_FILES:
        return True
    if path.parts[0] not in TOP:
        return False
    if any(
        p.lower()
        in {"archive", ".secrets", ".venv", "node_modules", "__pycache__", ".next"}
        or p.lower().startswith(".env")
        or "credential" in p.lower()
        for p in path.parts
    ):
        return False
    return (
        path.suffix in EXTENSIONS
        or path.name in {"Dockerfile", ".dockerignore"}
        or path.suffix == ".Dockerfile"
    )


def package(ref: str, output: Path) -> str:
    commit = (
        subprocess.check_output(
            ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"], cwd=ROOT
        )
        .decode()
        .strip()
    )
    listing = subprocess.check_output(["git", "ls-tree", "-rz", commit], cwd=ROOT)
    entries = []
    for entry in listing.split(b"\0"):
        if not entry:
            continue
        meta, raw_name = entry.split(b"\t", 1)
        mode, kind, oid = meta.decode().split()
        name = raw_name.decode("utf8")
        if not allowed(name):
            continue
        if kind != "blob" or mode not in {"100644", "100755"}:
            raise ValueError("Package refuses symlinks and submodules")
        entries.append((name, mode, oid))
    required = {
        "LICENSE",
        "web/package-lock.json",
        "api/uv.lock",
        "deploy/production/compose.yaml",
        "deploy/production/api.Dockerfile",
        "deploy/production/web.Dockerfile",
    }
    if not required <= {n for n, _, _ in entries}:
        raise ValueError("Commit does not contain the complete portable package")
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "commit": commit,
        "files": {},
        "runtime_acceptance": "not_established_by_packaging",
    }
    with (
        output.open("xb") as raw,
        gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as zipped,
        tarfile.open(fileobj=zipped, mode="w") as archive,
    ):
        for name, mode, oid in sorted(entries):
            size = int(
                subprocess.check_output(["git", "cat-file", "-s", oid], cwd=ROOT)
            )
            if size > 16 * 1024**2:
                raise ValueError("Unexpected oversized source blob")
            data = subprocess.check_output(["git", "cat-file", "blob", oid], cwd=ROOT)
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), int(mode[-3:], 8)
            archive.addfile(info, BytesIO(data))
            manifest["files"][name] = hashlib.sha256(data).hexdigest()
        data = json.dumps(manifest, sort_keys=True, indent=2).encode()
        info = tarfile.TarInfo("PACKAGE_MANIFEST.json")
        info.size, info.mode = len(data), 0o644
        archive.addfile(info, BytesIO(data))
    with output.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    output.with_suffix(output.suffix + ".sha256").write_text(
        digest + "\n", encoding="utf8"
    )
    return digest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument(
        "--output", type=Path, default=ROOT / ".secrets/artifacts/portable.tar.gz"
    )
    args = parser.parse_args()
    print(package(args.ref, args.output))
