"""Check local Markdown targets and keep private reference archives out of Git."""

from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    documents = [root / name for name in ("README.md", "AGENTS.md", "SECURITY.md")]
    documents.extend(sorted((root / "docs").rglob("*.md")))
    errors: list[str] = []
    for document in documents:
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", document.read_text("utf-8")):
            target = target.strip().strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or not parsed.path:
                continue
            resolved = (document.parent / unquote(parsed.path)).resolve()
            if not resolved.is_relative_to(root) or not resolved.exists():
                errors.append(f"{document.relative_to(root)}: invalid local target {target}")
    tracked = subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=root
    ).decode("utf-8").split("\0")
    errors.extend(
        f"Private archive tracked: {path}"
        for path in tracked
        if "archive" in Path(path).parts
    )
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Checked local links in {len(documents)} documents; no tracked archive.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
