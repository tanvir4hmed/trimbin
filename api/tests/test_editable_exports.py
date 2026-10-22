"""Deferred editable-export structural and integrity checks; not NLE acceptance."""

import copy
import hashlib
import json
from uuid import uuid4
from xml.etree import ElementTree as ET

import pytest

from app.evidence.contracts import EvidenceError
from app.exports import relink
from app.exports.formats import fcp7, manifest, timecode
from app.timeline.contracts import Clip, Sequence, conform


def example():
    source_id = str(uuid4())
    source = {
        "source_id": source_id,
        "sha256": "a" * 64,
        "filename": "scene & take.mov",
        "fps": {"numerator": 30000, "denominator": 1001},
        "frame_count": 300,
        "width": 1920,
        "height": 1080,
        "grid": "verified-cfr-v1",
        "timecode": "01:00:00;00",
        "audio": {
            "channels": 2,
            "sample_rate": "48000",
            "offset_seconds": {"numerator": 0, "denominator": 1},
        },
    }
    spec = Sequence(fps=source["fps"])
    clip = Clip(
        id=uuid4(), source_id=source_id, selection_id=uuid4(), in_frame=15, out_frame=45, gain_db=-6
    )
    first = conform(clip, source, spec, 0)
    second = conform(clip.model_copy(update={"id": uuid4(), "muted": True}), source, spec, 30)
    body = {
        "schema_version": "timeline-v1",
        "editor_approved": True,
        "sequence": spec.model_dump(),
        "clips": [first, second],
        "duration_frames": 60,
    }
    media = {
        source_id: {
            "root_alias": "library",
            "relative_path": "camera A/scene & take.mov",
            "sha256": "a" * 64,
            "video": {"sample_aspect_ratio": "1:1"},
            "audio_streams": 1,
        }
    }
    return body, media


def test_xml_repeated_occurrences_rates_links_and_timecode():
    body, media = example()
    root = ET.fromstring(fcp7(body, media, "film", 7))
    clips = root.findall(".//clipitem")
    assert len(clips) == 6 and len({c.attrib["id"] for c in clips}) == 6
    ids = {c.attrib["id"] for c in clips}
    assert all(link.text in ids for link in root.findall(".//linkclipref"))
    video = root.findall("./sequence/media/video/track/clipitem")
    assert [(c.findtext("in"), c.findtext("out")) for c in video] == [("15", "45")] * 2
    assert [c.findtext("start") for c in video] == ["0", "30"]
    assert root.findtext(".//file/timecode/frame") == "107892"
    assert root.findtext("./sequence/rate/ntsc") == "TRUE"
    assert len(root.findall(".//file/pathurl")) == 1
    assert "%20" in root.findtext(".//file/pathurl")
    assert (
        root.findall("./sequence/media/audio/track")[0].findall("clipitem")[1].findtext("enabled")
        == "FALSE"
    )
    assert timecode("00:01:00;02", body["sequence"]["fps"])[1] == 1800
    with pytest.raises(EvidenceError, match="label_invalid"):
        timecode("00:01:00;00", body["sequence"]["fps"])


def test_unsupported_audio_offset_kept_native_but_blocks_xml():
    body, media = example()
    for clip in body["clips"]:
        clip["source"] = copy.deepcopy(clip["source"])
        clip["source"]["audio"]["offset_seconds"] = {"numerator": 1, "denominator": 10}
    assert manifest(1, "film", 1, body, media)["timeline"] == body
    with pytest.raises(EvidenceError, match="audio_offset"):
        fcp7(body, media, "film", 1)
    body["clips"][0]["start_frame"] = 1
    with pytest.raises(EvidenceError, match="invalid_canonical"):
        manifest(1, "film", 1, body, media)


def test_relink_verifies_hashes_and_does_not_overwrite_original(tmp_path, monkeypatch):
    body, media = example()
    source_id = next(iter(media))
    root = tmp_path / "originals"
    source = root / "camera A" / "scene & take.mov"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"original fixture bytes")
    media[source_id]["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "timeline.json").write_text(json.dumps({"media": media}), encoding="utf-8")
    (bundle / "timeline.xml").write_bytes(fcp7(body, media, "film", 1))
    mapping = tmp_path / "roots.json"
    mapping.write_text(json.dumps({"library": str(root)}))
    monkeypatch.setattr(relink, "__file__", str(bundle / "relink.py"))
    monkeypatch.setattr("sys.argv", ["relink.py", "--roots", str(mapping)])
    relink.main()
    assert ET.parse(bundle / "timeline-relinked.xml").findtext(".//file/pathurl") == source.as_uri()
    assert source.read_bytes() == b"original fixture bytes"
    with pytest.raises(FileExistsError):
        relink.main()
    source.write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        relink.main()
