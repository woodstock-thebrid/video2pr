import subprocess
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.devin import create_session, get_session
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
        assert job["devin_state"] == "finished"
        assert job["devin_messages"]
        assert job["error"] is None
        assert any(client.get(path).status_code == 200 for path in job["frame_urls"])


def test_v1_normalizes_working_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVIN_API_KEY", "apk_legacy")
    monkeypatch.delenv("MOCK_DEVIN", raising=False)
    response = httpx.Response(
        200,
        json={
            "status_enum": "working",
            "pull_request": None,
            "messages": [{"message": "Investigating", "type": "agent", "timestamp": "2025-01-01T00:00:00Z"}],
        },
    )
    monkeypatch.setattr("backend.devin.httpx.get", lambda url, **kwargs: response)

    result = get_session("session-v1")

    assert result == {
        "state": "working",
        "pr_url": None,
        "messages": [
            {"message": "Investigating", "source": "agent", "timestamp": "2025-01-01T00:00:00Z"}
        ],
        "raw_status": "working",
    }


def test_v1_normalizes_blocked_and_pull_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVIN_API_KEY", "apk_user_legacy")
    monkeypatch.delenv("MOCK_DEVIN", raising=False)
    response = httpx.Response(
        200,
        json={
            "status_enum": "blocked",
            "pull_request": {"url": "https://github.com/example/repo/pull/12"},
            "messages": [],
        },
    )
    monkeypatch.setattr("backend.devin.httpx.get", lambda url, **kwargs: response)

    result = get_session("session-v1")

    assert result["state"] == "waiting_for_user"
    assert result["pr_url"] == "https://github.com/example/repo/pull/12"


def test_v3_create_uses_org_repo_and_no_title(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVIN_API_KEY", "cog_test")
    monkeypatch.setenv("DEVIN_ORG_ID", "org-test")
    monkeypatch.setenv("TARGET_REPO", "owner/project")
    monkeypatch.delenv("MOCK_DEVIN", raising=False)
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        calls.append((url, kwargs))
        return httpx.Response(200, json={"session_id": "session-v3", "url": "https://app.devin.ai/session-v3"})

    monkeypatch.setattr("backend.devin.httpx.post", fake_post)

    result = create_session("prompt text", "A title v3 does not send")

    assert result == {"session_id": "session-v3", "url": "https://app.devin.ai/session-v3"}
    assert calls[0][0] == "https://api.devin.ai/v3/organizations/org-test/sessions"
    assert calls[0][1]["json"] == {
        "prompt": "prompt text",
        "tags": ["video2pr"],
        "repos": ["owner/project"],
    }


def test_v3_normalizes_waiting_for_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVIN_API_KEY", "cog_test")
    monkeypatch.setenv("DEVIN_ORG_ID", "org-test")
    monkeypatch.delenv("MOCK_DEVIN", raising=False)
    responses = iter(
        [
            httpx.Response(
                200,
                json={"status": "running", "status_detail": "waiting_for_approval", "pull_requests": []},
            ),
            httpx.Response(
                200,
                json={"items": [{"message": "Please approve access", "source": "devin", "created_at": 1735689600}]},
            ),
        ]
    )
    calls: list[str] = []

    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        calls.append(url)
        return next(responses)

    monkeypatch.setattr("backend.devin.httpx.get", fake_get)

    result = get_session("session-v3")

    assert result == {
        "state": "waiting_for_user",
        "pr_url": None,
        "messages": [{"message": "Please approve access", "source": "devin", "timestamp": 1735689600}],
        "raw_status": "running:waiting_for_approval",
    }
    assert calls[1].endswith("/sessions/session-v3/messages?first=100")


def test_v3_normalizes_running_and_pull_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVIN_API_KEY", "cog_test")
    monkeypatch.setenv("DEVIN_ORG_ID", "org-test")
    monkeypatch.delenv("MOCK_DEVIN", raising=False)
    responses = iter(
        [
            httpx.Response(
                200,
                json={
                    "status": "running",
                    "status_detail": "working",
                    "pull_requests": [{"pr_url": "https://github.com/example/repo/pull/18", "pr_state": "open"}],
                },
            ),
            httpx.Response(200, json={"items": []}),
        ]
    )
    monkeypatch.setattr("backend.devin.httpx.get", lambda url, **kwargs: next(responses))

    result = get_session("session-v3")

    assert result == {
        "state": "working",
        "pr_url": "https://github.com/example/repo/pull/18",
        "messages": [],
        "raw_status": "running:working",
    }


def test_v3_normalizes_error_and_pull_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVIN_API_KEY", "cog_test")
    monkeypatch.delenv("MOCK_DEVIN", raising=False)
    responses = iter(
        [
            httpx.Response(
                200,
                json={
                    "status": "error",
                    "status_detail": None,
                    "pull_requests": [],
                },
            ),
            httpx.Response(200, json={"items": []}),
        ]
    )
    monkeypatch.setattr("backend.devin.httpx.get", lambda url, **kwargs: next(responses))

    result = get_session("session-v3")

    assert result["state"] == "failed"
    assert result["pr_url"] is None
    assert result["raw_status"] == "error"


def test_http_errors_include_path_status_and_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVIN_API_KEY", "apk_legacy")
    monkeypatch.delenv("MOCK_DEVIN", raising=False)
    monkeypatch.setattr(
        "backend.devin.httpx.get",
        lambda url, **kwargs: httpx.Response(403, text="permission denied"),
    )

    with pytest.raises(RuntimeError, match=r"GET /v1/sessions/session-v1 -> 403: permission denied"):
        get_session("session-v1")
