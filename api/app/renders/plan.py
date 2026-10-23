"""Explicit original-resolution SDR render contract; no automatic quality fallback."""

from fractions import Fraction

from ..evidence.contracts import EvidenceError
from ..exports.formats import validated as canonical_validated
from ..timeline.contracts import nearest

VERSION = "original-render-v1"


def validated(body: dict) -> None:
    canonical_validated(body)
    seq = body["sequence"]
    for clip in body["clips"]:
        source = clip["source"]
        if source["fps"] != seq["fps"]:
            raise EvidenceError("render_mixed_rate_not_supported")
        if (source["width"], source["height"]) != (seq["width"], seq["height"]):
            raise EvidenceError("render_scaling_not_supported")
        if seq["width"] % 2 or seq["height"] % 2:
            raise EvidenceError("render_even_dimensions_required")
        color = source["color"]
        if (
            any(
                color.get(k) != "bt709"
                for k in ("color_space", "color_transfer", "color_primaries")
            )
            or color.get("color_range") != "tv"
            or color.get("pix_fmt") != "yuv420p"
        ):
            raise EvidenceError("render_requires_explicit_rec709_8bit_420_limited")
        audio = source.get("audio")
        if audio and audio["channels"] not in (1, 2):
            raise EvidenceError("render_audio_layout_not_supported")


def samples(clip: dict, fps: Fraction) -> int:
    # Round cumulative boundaries, so repeated fractional-rate cuts do not drift.
    return nearest(Fraction(clip["start_frame"] + clip["duration_frames"]) * 48000 / fps) - nearest(
        Fraction(clip["start_frame"]) * 48000 / fps
    )


def filters(clip: dict, fps: Fraction) -> tuple[str, str]:
    video = f"trim=start_frame={clip['in_frame']}:end_frame={clip['out_frame']},setpts=N/({fps})/TB"
    count = samples(clip, fps)
    audio = clip["source"].get("audio")
    if clip["muted"] or not audio:
        return video, f"anullsrc=r=48000:cl=stereo,atrim=end_sample={count},asetpts=N/SR/TB"
    start = Fraction(clip["in_frame"]) / fps - Fraction(**audio["offset_seconds"])
    skip = nearest(max(Fraction(0), start) * 48000)
    delay = nearest(max(Fraction(0), -start) * 48000)
    if delay >= count:
        return video, f"anullsrc=r=48000:cl=stereo,atrim=end_sample={count},asetpts=N/SR/TB"
    layout = "pan=stereo|c0=c0|c1=c0," if audio["channels"] == 1 else ""
    af = (
        f"[0:{int(audio['stream_index'])}]aresample=48000,{layout}"
        f"atrim=start_sample={skip},asetpts=N/SR/TB,adelay={delay}S:all=1,"
        f"volume={float(clip['gain_db'])}dB,apad=whole_len={count},atrim=end_sample={count},asetpts=N/SR/TB"
    )
    return video, af
