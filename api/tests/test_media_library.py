"""Source safety, playback authority and real small-corpus FFmpeg acceptance."""

import shutil
import subprocess
import time
from fractions import Fraction
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from app.config import Settings
from app.media import tickets
from app.media.files import MediaError, MediaPaths, byte_range, digest_file, safe_path
from app.media.processing import derivatives, probe, rational, run_process, seconds, source_metadata
from app.routes import media_library as routes


@pytest.fixture
def config(tmp_path):
    mounted = tmp_path / "camera"
    mounted.mkdir()
    return Settings(
        _env_file=None,
        originals_root=str(tmp_path / "originals"),
        proxies_root=str(tmp_path / "derived"),
        staging_root=str(tmp_path / "staging"),
        allowed_media_roots=[str(tmp_path / "originals"), str(mounted)],
        media_roots={"camera": str(mounted)},
        media_root_projects={"camera": [7]},
        media_work_bytes=32 * 1024**2,
        media_reserve_bytes=0,
        session_secret="s" * 64,
    )


@pytest.mark.parametrize(
    "name",
    [
        "../private.mov",
        "/etc/password",
        "x/../a.mov",
        "C:/x.mov",
        "x\\y.mov",
        "x.mov:secret",
        "CON.mp4",
        "a./b.mov",
    ],
)
def test_paths_refuse_platform_independent_escapes(config, name):
    paths = MediaPaths(config)
    with pytest.raises(MediaError):
        paths.resolve(7, "camera", name, exists=False)


def test_project_root_isolation_and_duplicate_basenames(config):
    paths = MediaPaths(config)
    root = paths.roots["camera"]
    for folder in ("a", "b"):
        (root / folder).mkdir()
        (root / folder / "take.mp4").write_bytes(folder.encode())
    assert paths.resolve(7, "camera", "a/take.mp4") != paths.resolve(7, "camera", "b/take.mp4")
    with pytest.raises(MediaError, match="root_not_allowed"):
        paths.resolve(8, "camera", "a/take.mp4")
    with pytest.raises(MediaError, match="root_not_allowed"):
        paths.resolve(8, "uploads", "p7/asset/take.mp4", exists=False)


def test_symlink_escape_is_refused(config, tmp_path):
    paths = MediaPaths(config)
    private = tmp_path / "private.mp4"
    private.write_bytes(b"private")
    link = paths.roots["camera"] / "link.mp4"
    try:
        link.symlink_to(private)
    except OSError:
        pytest.skip("Host cannot create symlinks; Linux CI runs this check")
    with pytest.raises(MediaError, match="media_link_forbidden"):
        paths.resolve(7, "camera", "link.mp4")


def test_derivatives_cannot_overlap_sources(config):
    config.proxies_root = str(Path(config.originals_root) / "cache")
    with pytest.raises(MediaError, match="media_roots_overlap"):
        MediaPaths(config)


def test_root_remap_and_missing_source(config, tmp_path):
    paths = MediaPaths(config)
    original = paths.roots["camera"] / "take.mov"
    original.write_bytes(b"unchanged")
    expected = digest_file(original)
    moved = tmp_path / "moved"
    paths.roots["camera"].rename(moved)
    config.media_roots["camera"] = str(moved)
    config.allowed_media_roots = [config.originals_root, str(moved)]
    assert digest_file(MediaPaths(config).resolve(7, "camera", "take.mov")) == expected
    with pytest.raises(FileNotFoundError):
        safe_path(moved, "missing.mov")


def test_hash_detects_changes_during_read(tmp_path):
    path = tmp_path / "source"
    path.write_bytes(b"a" * (2 * 1024**2))
    changed = False

    def mutate():
        nonlocal changed
        if not changed:
            changed = True
            with path.open("ab") as handle:
                handle.write(b"changed")

    with pytest.raises(MediaError, match="source_changed"):
        digest_file(path, mutate)


@pytest.mark.parametrize(
    "header,expected",
    [
        (None, (0, 9, False)),
        ("bytes=2-4", (2, 4, True)),
        ("bytes=8-", (8, 9, True)),
        ("bytes=-3", (7, 9, True)),
        ("bytes=0-99", (0, 9, True)),
    ],
)
def test_ranges(header, expected):
    assert byte_range(header, 10) == expected


@pytest.mark.parametrize(
    "header", ["bytes=10-", "bytes=4-2", "bytes=0-2,4-6", "bytes=-0", "bytes=-", "garbage"]
)
def test_invalid_ranges(header):
    with pytest.raises(MediaError, match="invalid_range"):
        byte_range(header, 10)


def test_ticket_expiry_scope_and_tampering():
    secret, source = "s" * 64, str(uuid4())
    token = tickets.issue(secret, 7, source, "proxy")
    tickets.verify(secret, 7, source, "proxy", token)
    for project, asset, kind, candidate in [
        (8, source, "proxy", token),
        (7, str(uuid4()), "proxy", token),
        (7, source, "original", token),
        (7, source, "proxy", token + "x"),
        (7, source, "proxy", tickets.issue(secret, 7, source, "proxy", int(time.time()) - 1)),
    ]:
        with pytest.raises(MediaError, match="invalid_media_ticket"):
            tickets.verify(secret, project, asset, kind, candidate)


def test_exact_metadata_retains_rational_timecode_and_audio():
    meta = source_metadata(
        {
            "format": {"format_name": "mov", "duration": "1.001"},
            "streams": [
                {
                    "codec_type": "video",
                    "width": 320,
                    "height": 180,
                    "avg_frame_rate": "24000/1001",
                    "r_frame_rate": "24000/1001",
                    "time_base": "1/24000",
                    "start_pts": 48000,
                    "start_time": "2",
                    "tags": {"timecode": "01:00:00:00"},
                },
                {
                    "codec_type": "audio",
                    "sample_rate": "48000",
                    "channels": 2,
                    "start_time": "2.25",
                },
            ],
        },
        100,
    )
    assert seconds(meta["frame_rate"]) == Fraction(24000, 1001)
    assert abs(seconds(meta["video_start"]) - 2) < Fraction(1, 24)
    assert meta["timecode"] == "01:00:00:00"
    assert meta["audio"][0]["start_time"] == "2.25"
    with pytest.raises(MediaError):
        rational("0/0")


@pytest.fixture
def route_app(config, monkeypatch):
    paths = MediaPaths(config)
    source_id = uuid4()
    (paths.roots["camera"] / "take.mp4").write_bytes(b"0123456789")
    row = {
        "id": source_id,
        "project_id": 7,
        "root_alias": "camera",
        "relative_path": "take.mp4",
        "filename": "take.mp4",
        "state": "queued",
        "stage": "queued",
        "derivatives": None,
    }

    class Store:
        def get(self, project, asset):
            if project != 7 or asset != source_id:
                raise MediaError("source_not_found")
            return row

    class User:
        email = "editor@example.test"
        is_anonymous = False

        async def assert_can_read(self, project):
            if project != 7:
                raise HTTPException(403)

    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.current_principal] = lambda: User()
    app.dependency_overrides[routes.require_signed_in] = lambda: User()

    @app.exception_handler(MediaError)
    async def error(request, exc):
        return JSONResponse({"detail": exc.code}, status_code=403)

    monkeypatch.setattr(routes, "runtime", lambda: (paths, Store()))

    async def authorize(principal, project, permission):
        await principal.assert_can_read(project)

    monkeypatch.setattr(routes, "authorize", authorize)
    monkeypatch.setattr(routes, "settings", config)
    return app, source_id


async def test_authenticated_range_playback_and_scoped_ticket(route_app):
    app, asset = route_app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        path = f"/media-library/7/sources/{asset}"
        response = await client.get(f"{path}/file/original", headers={"Range": "bytes=2-4"})
        assert response.status_code == 206 and response.content == b"234"
        assert response.headers["content-range"] == "bytes 2-4/10"
        assert (
            await client.get(f"/media-library/8/sources/{asset}/file/original")
        ).status_code == 403
        assert (
            await client.get(f"{path}/file/original", headers={"Range": "bytes=12-"})
        ).status_code == 416
        url = (await client.post(f"{path}/access/original")).json()["url"]
        assert (await client.get(url)).content == b"0123456789"
        assert (await client.get(url.replace("/7/", "/8/"))).status_code == 403
        assert (await client.head(f"{path}/file/original")).headers["content-length"] == "10"


@pytest.fixture
def footage(tmp_path):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg/ffprobe required for media acceptance")
    path = tmp_path / "fractional.mov"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=24000/1001",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000",
            "-t",
            "2.002",
            "-c:v",
            "libx264",
            "-threads",
            "2",
            "-c:a",
            "aac",
            "-timecode",
            "01:00:00:00",
            str(path),
        ],
        check=True,
        timeout=30,
        capture_output=True,
    )
    return path


async def test_real_derivatives_keep_original_and_timing(config, footage, tmp_path):
    original = digest_file(footage)
    metadata = source_metadata(await probe(footage), footage.stat().st_size)
    work = tmp_path / "work"
    work.mkdir()
    stages = []
    result = await derivatives(footage, work, metadata, config, lambda: None, stages.append)
    assert digest_file(footage) == original
    assert seconds(result["proxy_metadata"]["frame_rate"]) == Fraction(24000, 1001)
    assert seconds(result["proxy_metadata"]["duration"]) == seconds(metadata["duration"])
    assert result["proxy_metadata"]["video"]["nb_frames"] == metadata["video"]["nb_frames"]
    assert metadata["timecode"] == "01:00:00:00"
    assert all((work / result[kind]).stat().st_size > 0 for kind in ("proxy", "sprite", "audio"))
    assert (await probe(work / "audio.flac"))["streams"][0]["sample_rate"] == "48000"
    assert stages == ["encoding_proxy", "building_sprite", "extracting_audio"]


async def test_corrupt_file_fails_explicitly(tmp_path):
    if not shutil.which("ffprobe"):
        pytest.skip("ffprobe unavailable")
    path = tmp_path / "bad.mov"
    path.write_bytes(b"not video")
    with pytest.raises(MediaError, match="media_decode_failed"):
        await probe(path)


async def test_nonzero_video_origin_and_delayed_audio(config, footage, tmp_path):
    shifted = tmp_path / "shifted.mov"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(footage),
            "-vf",
            "setpts=PTS+2/TB",
            "-af",
            "asetpts=PTS+2.25/TB",
            "-c:v",
            "libx264",
            "-threads",
            "2",
            "-c:a",
            "aac",
            "-fps_mode",
            "passthrough",
            str(shifted),
        ],
        check=True,
        timeout=30,
        capture_output=True,
    )
    meta = source_metadata(await probe(shifted), shifted.stat().st_size)
    assert abs(seconds(meta["video_start"]) - 2) < Fraction(1, 24)
    work = tmp_path / "shift-work"
    work.mkdir()
    result = await derivatives(shifted, work, meta, config, lambda: None, lambda _: None)
    original_offset = Fraction(meta["audio"][0]["start_time"]) - seconds(meta["video_start"])
    proxy_offset = Fraction(result["proxy_metadata"]["audio"][0]["start_time"])
    # AAC encoding adds up to one 1024-sample priming frame.
    assert abs(proxy_offset - original_offset) <= Fraction(1025, 48000)


async def test_processing_disk_budget_is_enforced(tmp_path):
    import sys

    with pytest.raises(MediaError, match="media_work_limit_exceeded"):
        await run_process(
            [
                sys.executable,
                "-c",
                "from pathlib import Path; import sys; Path(sys.argv[1]).write_bytes(b'x'*4096)",
                str(tmp_path / "output"),
            ],
            timeout=10,
            check=lambda: None,
            work=tmp_path,
            budget=100,
        )


async def test_process_lease_loss_terminates_child():
    import sys

    checks = 0

    def cancelled():
        nonlocal checks
        checks += 1
        if checks > 1:
            raise MediaError("lease_lost")

    started = time.monotonic()
    with pytest.raises(MediaError, match="lease_lost"):
        await run_process(
            [sys.executable, "-c", "import time; time.sleep(30)"], timeout=10, check=cancelled
        )
    assert time.monotonic() - started < 5
