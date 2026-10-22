"""Run beside timeline.xml to relink originals locally; no uploads or re-encoding."""

import argparse
import hashlib
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--roots", required=True, help="JSON mapping root aliases to absolute folders"
    )
    args = parser.parse_args()
    directory = Path(__file__).resolve().parent
    manifest_path = directory / "timeline.json"
    xml_path = directory / "timeline.xml"
    if max(manifest_path.stat().st_size, xml_path.stat().st_size) > 32 * 1024**2:
        raise ValueError("Oversized export document")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    roots = json.loads(Path(args.roots).read_text(encoding="utf-8"))
    raw = xml_path.read_bytes()
    if re.search(rb"<!ENTITY|<!DOCTYPE\s+[^>]*(?:SYSTEM|PUBLIC|\[)", raw, re.IGNORECASE):
        raise ValueError("External declarations are not accepted")
    tree = ET.fromstring(raw)
    sources = {}
    for source_id, media in manifest["media"].items():
        base = Path(roots[media["root_alias"]]).expanduser()
        if not base.is_absolute():
            raise ValueError("Every root must be an absolute local folder")
        base = base.resolve(strict=True)
        relative = media["relative_path"]
        if (
            "\\" in relative
            or ":" in relative
            or any(p in {"", ".", ".."} for p in relative.split("/"))
        ):
            raise ValueError("Invalid relative media path")
        path = base.joinpath(*relative.split("/")).resolve(strict=True)
        if not path.is_relative_to(base) or not path.is_file():
            raise ValueError("Media must remain inside its assigned root")
        with path.open("rb") as handle:
            actual = hashlib.file_digest(handle, "sha256").hexdigest()
        if actual != media["sha256"]:
            raise ValueError("Original hash mismatch for source " + source_id)
        sources["file-" + source_id] = path
    for file in tree.findall(".//file"):
        url = file.find("pathurl")
        if url is not None:
            url.text = sources[file.attrib["id"]].as_uri()
    output = directory / "timeline-relinked.xml"
    if output.resolve() in sources.values():
        raise ValueError("Output would overwrite original")
    ET.indent(tree)
    with output.open("xb") as handle:
        handle.write(b'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n')
        handle.write(ET.tostring(tree, encoding="utf-8"))
    print(
        "Original hashes verified. Created timeline-relinked.xml; "
        "import into Premiere and verify the edit."
    )


if __name__ == "__main__":
    main()
