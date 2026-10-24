import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.jobs import JOBS
from backend.report import BugReport, parse_report_json
from backend.video import extract_frames


@pytest.fixture(scope="module")
def sample_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    video_path = tmp_path_factory.mktemp("video") / "screen-recording.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=20:size=640x360:rate=10",
            "-pix_fmt",
            "yuv420p",
            str(video_path),
        ],
        check=True,
        capture_output=True,
    )
    return video_path


def test_extract_frames_samples_long_video_within_limit(sample_video: Path, tmp_path: Path) -> None:
    frames = extract_frames(sample_video, tmp_path / "frames")

    assert len(frames) <= 12
    assert frames
    assert all(frame.is_file() and frame.stat().st_size for frame in frames)


def test_parse_json_fence() -> None:
    report = parse_report_json(
        """```json
{"title":"Cart total is wrong","page":"Checkout","steps":["Add two burgers"],"expected":"$25","actual":"$12.50","suspected_area":"Cart totals","severity":"high"}
```"""
    )

    assert isinstance(report, BugReport)
    assert report.title == "Cart total is wrong"
    assert report.steps == ["Add two burgers"]


def test_mock_pipeline_returns_pr(monkeypatch: pytest.MonkeyPatch, sample_video: Path) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("DEVIN_API_KEY", raising=False)
    monkeypatch.setenv("MOCK_DEVIN", "1")
    monkeypatch.setenv("MOCK_DEVIN_SECONDS", "0.1")
    monkeypatch.setenv("DEVIN_POLL_SECONDS", "0.05")
    JOBS.clear()

    with TestClient(app) as client:
        with sample_video.open("rb") as video:
            response = client.post(
                "/api/reports",
                files={"video": ("recording.mp4", video, "video/mp4")},
                data={"note": "The total should include every item."},
            )
        assert response.status_code == 200
        job_id = response.json()["job_id"]

        deadline = time.monotonic() + 10
        job = client.get(f"/api/reports/{job_id}").json()
        while job["stage"] not in {"pr_opened", "finished", "failed"} and time.monotonic() < deadline:
            time.sleep(0.05)
            job = client.get(f"/api/reports/{job_id}").json()

        assert job["stage"] in {"pr_opened", "finished"}, job
        assert job["report"]["title"]
        assert job["frame_urls"]
        assert job["pr_url"]
        assert job["devin_session_url"]
        assert job["devin_messages"]
        assert job["error"] is None
        assert any(client.get(path).status_code == 200 for path in job["frame_urls"])
