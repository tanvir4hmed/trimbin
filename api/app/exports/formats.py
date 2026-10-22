"""Deterministic native manifest and bounded FCP7 XMEML v5 writer."""

import re
from fractions import Fraction
from urllib.parse import quote
from xml.etree import ElementTree as ET

from ..evidence.contracts import EvidenceError
from ..inference.contracts import fingerprint
from ..media.files import relative_name
from ..timeline.contracts import Clip, Sequence, conform

VERSION = "editable-export-v1"


def rate_value(fps: dict) -> tuple[int, bool]:
    value = Fraction(**fps)
    if value.denominator == 1 and value.numerator in {24, 25, 30, 50, 60}:
        return value.numerator, False
    if value in {Fraction(24000, 1001), Fraction(30000, 1001), Fraction(60000, 1001)}:
        return int(value * Fraction(1001, 1000)), True
    raise EvidenceError("xml_rate_unsupported")


def timecode(label: str | None, fps: dict) -> tuple[str, int, str]:
    nominal, ntsc = rate_value(fps)
    label = label or "00:00:00:00"
    match = re.fullmatch(r"(\d{2}):(\d{2}):(\d{2})([:;])(\d{2})", label)
    if not match:
        raise EvidenceError("xml_timecode_unsupported")
    h, m, s, f = (int(match[i]) for i in (1, 2, 3, 5))
    drop = match[4] == ";"
    if h >= 24 or m >= 60 or s >= 60 or f >= nominal:
        raise EvidenceError("xml_timecode_invalid")
    if drop and (not ntsc or nominal != 30):
        raise EvidenceError("xml_drop_frame_rate_unsupported")
    if drop and m % 10 and s == 0 and f < 2:
        raise EvidenceError("xml_drop_frame_label_invalid")
    count = ((h * 60 + m) * 60 + s) * nominal + f
    if drop:
        count -= 2 * (h * 60 + m - (h * 60 + m) // 10)
    return label, count, "DF" if drop else "NDF"


def validated(body: dict) -> None:
    if body.get("schema_version") != "timeline-v1" or not body.get("editor_approved"):
        raise EvidenceError("approved_timeline_required")
    if not body["clips"] or len(body["clips"]) > 1000:
        raise EvidenceError("export_requires_1_to_1000_occurrences")
    sequence = Sequence.model_validate(body["sequence"])
    seen, start = set(), 0
    for entry in body["clips"]:
        clip = Clip.model_validate({k: entry[k] for k in Clip.model_fields})
        expected = conform(clip, entry["source"], sequence, start)
        if clip.id in seen or any(
            entry[k] != expected[k]
            for k in ("start_frame", "duration_frames", "quantization_seconds")
        ):
            raise EvidenceError("invalid_canonical_timeline")
        if entry["source"]["grid"] != "verified-cfr-v1":
            raise EvidenceError("source_timing_not_verified")
        seen.add(clip.id)
        start += entry["duration_frames"]
    if body["duration_frames"] != start:
        raise EvidenceError("invalid_canonical_timeline")


def xml_preflight(body: dict, media: dict) -> None:
    validated(body)
    sequence = body["sequence"]
    rate_value(sequence["fps"])
    for clip in body["clips"]:
        source = clip["source"]
        if Fraction(**source["fps"]) != Fraction(**sequence["fps"]):
            raise EvidenceError("xml_mixed_rate_acceptance_pending")
        if (source["width"], source["height"]) != (sequence["width"], sequence["height"]):
            raise EvidenceError("xml_scaling_acceptance_pending")
        video = media[clip["source_id"]]["video"]
        if video.get("sample_aspect_ratio") not in {"1:1", "1/1"}:
            raise EvidenceError("xml_pixel_aspect_unsupported")
        if any(s.get("rotation", 0) != 0 for s in video.get("side_data_list", [])):
            raise EvidenceError("xml_rotation_unsupported")
        if video.get("field_order") not in {None, "unknown", "progressive"}:
            raise EvidenceError("xml_interlaced_unsupported")
        timecode(source.get("timecode"), source["fps"])
        audio = source.get("audio")
        if audio and (
            audio["channels"] not in {1, 2} or media[clip["source_id"]]["audio_streams"] != 1
        ):
            raise EvidenceError("xml_audio_layout_unsupported")
        if audio and Fraction(**audio["offset_seconds"]) != 0:
            raise EvidenceError("xml_audio_offset_acceptance_pending")


def add(parent, name, text=None, **attrs):
    node = ET.SubElement(parent, name, attrs)
    if text is not None:
        text = str(text)
        if any(ord(c) < 32 and c not in "\t\n\r" for c in text):
            raise EvidenceError("xml_text_invalid")
        node.text = text
    return node


def rate(parent, fps):
    nominal, ntsc = rate_value(fps)
    node = add(parent, "rate")
    add(node, "timebase", nominal)
    add(node, "ntsc", "TRUE" if ntsc else "FALSE")


def tc(parent, label, fps):
    label, frames, display = timecode(label, fps)
    node = add(parent, "timecode")
    rate(node, fps)
    add(node, "string", label)
    add(node, "frame", frames)
    add(node, "displayformat", display)


def dimensions(parent, source):
    add(parent, "width", source["width"])
    add(parent, "height", source["height"])
    add(parent, "pixelaspectratio", "square")
    add(parent, "anamorphic", "FALSE")


def fcp7(body: dict, media: dict, sequence_id: str, revision: int) -> bytes:
    xml_preflight(body, media)
    root = ET.Element("xmeml", version="5")
    sequence = add(root, "sequence", id=f"sequence-{sequence_id}-r{revision}")
    spec = body["sequence"]
    add(sequence, "name", f"{spec['name']} r{revision}")
    add(sequence, "duration", body["duration_frames"])
    rate(sequence, spec["fps"])
    tc(sequence, None, spec["fps"])
    tracks = add(sequence, "media")
    video = add(tracks, "video")
    fmt = add(add(video, "format"), "samplecharacteristics")
    rate(fmt, spec["fps"])
    dimensions(fmt, spec)
    video_track = add(video, "track")
    audio = add(tracks, "audio")
    add(audio, "numOutputChannels", 2)
    audio_fmt = add(add(audio, "format"), "samplecharacteristics")
    add(audio_fmt, "depth", 32)
    add(audio_fmt, "samplerate", 48000)
    audio_tracks = [add(audio, "track"), add(audio, "track")]
    for i, track in enumerate(audio_tracks, 1):
        add(track, "outputchannelindex", i)
    defined = set()
    for occurrence in body["clips"]:
        source = occurrence["source"]
        source_id = occurrence["source_id"]
        source_channels = source["audio"]["channels"] if source.get("audio") else 0
        # Mono maps equally to L/R, stereo keeps its separate source channels.
        channels = 2 if source_channels else 0
        ids = [
            f"v-{occurrence['id']}",
            *[f"a{i}-{occurrence['id']}" for i in range(1, channels + 1)],
        ]
        for channel, ident in enumerate(ids):
            item = add(
                video_track if channel == 0 else audio_tracks[channel - 1], "clipitem", id=ident
            )
            add(item, "name", source["filename"])
            add(item, "duration", source["frame_count"])
            rate(item, source["fps"])
            add(item, "start", occurrence["start_frame"])
            add(item, "end", occurrence["start_frame"] + occurrence["duration_frames"])
            add(item, "in", occurrence["in_frame"])
            add(item, "out", occurrence["out_frame"])
            add(item, "enabled", "FALSE" if channel and occurrence["muted"] else "TRUE")
            file = add(item, "file", id=f"file-{source_id}")
            if source_id not in defined:
                defined.add(source_id)
                reference = media[source_id]
                relative = relative_name(f"{reference['root_alias']}/{reference['relative_path']}")
                add(file, "name", source["filename"])
                add(file, "pathurl", "file://localhost/TRIMBIN_MEDIA/" + quote(relative, safe="/"))
                rate(file, source["fps"])
                add(file, "duration", source["frame_count"])
                tc(file, source.get("timecode"), source["fps"])
                fm = add(file, "media")
                fv = add(add(fm, "video"), "samplecharacteristics")
                rate(fv, source["fps"])
                dimensions(fv, source)
                if channels:
                    fa = add(fm, "audio")
                    add(fa, "channelcount", source_channels)
                    fs = add(fa, "samplecharacteristics")
                    add(fs, "samplerate", source["audio"]["sample_rate"])
            if channel:
                st = add(item, "sourcetrack")
                add(st, "mediatype", "audio")
                add(st, "trackindex", min(channel, source_channels))
                effect = add(add(item, "filter"), "effect")
                for k, v in {
                    "name": "Audio Levels",
                    "effectid": "audiolevels",
                    "effectcategory": "audio",
                    "effecttype": "audio",
                    "mediatype": "audio",
                }.items():
                    add(effect, k, v)
                param = add(effect, "parameter")
                add(param, "parameterid", "level")
                add(param, "name", "Level")
                add(param, "value", format(10 ** (occurrence["gain_db"] / 20), ".12g"))
            for linked in ids:
                add(add(item, "link"), "linkclipref", linked)
    ET.indent(root)
    return b'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n' + ET.tostring(
        root, encoding="utf-8"
    )


def manifest(project: int, key: str, revision: int, body: dict, media: dict) -> dict:
    validated(body)
    return {
        "schema_version": VERSION,
        "project_id": project,
        "sequence_id": key,
        "revision": revision,
        "snapshot_sha256": fingerprint(body),
        "timeline": body,
        "media": media,
        "originals_included": False,
        "premiere_import_verified": False,
        "timecode_policy": "Missing source timecode uses zero only in XML; native retains null.",
    }
