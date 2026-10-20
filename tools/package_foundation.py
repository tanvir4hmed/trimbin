"""Build a private release artifact from Git-tracked source, never local secrets/media."""

import gzip
import hashlib
import subprocess
import tarfile
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    target = ROOT / ".secrets" / "artifacts"
    target.mkdir(parents=True, exist_ok=True)
    output = target / "foundation.tar.gz"
    names = (
        subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
        .decode()
        .split("\0")
    )
    with (
        output.open("wb") as raw,
        gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as zipped,
        tarfile.open(fileobj=zipped, mode="w") as archive,
    ):
        for name in sorted(filter(None, names)):
            path = Path(name)
            if (
                path.parts[0]
                not in {
                    "api",
                    "agents",
                    "clickhouse",
                    "deploy",
                    "tools",
                }
                and name != ".env.example"
            ):
                continue
            source = ROOT / path
            if not source.is_file() or source.is_symlink():
                raise ValueError(f"Expected tracked regular source: {name}")
            data = source.read_bytes()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o644
            archive.addfile(info, BytesIO(data))
    with output.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    (target / "foundation.sha256").write_text(digest, encoding="utf-8")
    print(f"Source artifact: {output}\nSHA256: {digest}")


if __name__ == "__main__":
    main()
