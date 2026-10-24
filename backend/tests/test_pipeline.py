import asyncio
import json
import subprocess
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.devin import build_session_schema, build_vision_prompt, create_session, get_session, upload_attachment
from backend.main import app
from backend.jobs import JOBS, _poll_session, extract_before_after
from backend.report import BugReport, parse_report_json, select_vision_provider
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


def test_session_schema_has_optional_comparison_fields() -> None:
    schema = build_session_schema()

    assert "$ref" not in json.dumps(schema)
    assert set(schema["required"]) == {
        "title", "page", "steps", "expected", "actual", "suspected_area", "severity"
    }
    assert all(
        schema["properties"][name]["type"] == "string"
        for name in ("before_screenshot_url", "after_screenshot_url", "root_cause", "code_diff")
    )
    assert not set(("before_screenshot_url", "after_screenshot_url", "root_cause", "code_diff")) & set(schema["required"])


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("![AFTER](https://img/after.png) ![Before](https://img/before.png)",
         ("https://img/before.png", "https://img/after.png")),
        ("![one](https://img/one.png) ![two](https://img/two.png)",
         ("https://img/one.png", "https://img/two.png")),
        ('<img alt="after" src="https://img/after.png"><img src="https://img/before.png" alt="before">',
         ("https://img/before.png", "https://img/after.png")),
        ("No screenshots here.", (None, None)),
    ],
)
def test_extract_before_after(body: str, expected: tuple[str | None, str | None]) -> None:
    assert extract_before_after(body) == expected


def test_polling_continues_after_pr_until_comparison_is_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVIN_POLL_SECONDS", "0.01")
    responses = iter(
        [
            {"state": "working", "pr_url": "https://github.com/example/repo/pull/9", "messages": [], "structured_output": None},
            {
                "state": "working",
                "pr_url": "https://github.com/example/repo/pull/9",
                "messages": [],
                "structured_output": {
                    "before_screenshot_url": "https://img/before.png",
                    "after_screenshot_url": "https://img/after.png",
                    "root_cause": "Quantity was omitted.",
                    "code_diff": "-old\n+new",
                },
            },
        ]
    )
    monkeypatch.setattr("backend.jobs.get_session", lambda _session_id: next(responses))
    job: dict[str, object] = {
        "stage": "devin_working", "timestamps": {}, "report": {"title": "Bug"},
        "devin_messages": [], "devin_state": None, "pr_url": None,
        "comparison": None, "comparison_status": None,
    }

    asyncio.run(_poll_session(job, "real-session", devin_vision=False))

    assert job["stage"] == "pr_opened"
    assert job["comparison_status"] == "ready"
    assert job["comparison"]["before_url"] == "https://img/before.png"
    assert job["comparison"]["root_cause"] == "Quantity was omitted."


def test_comparison_timeout_falls_back_to_pr_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVIN_POLL_SECONDS", "0.01")
    monkeypatch.setenv("COMPARISON_TIMEOUT_SECONDS", "0")
    monkeypatch.setenv("GITHUB_TOKEN", "github-test")
    monkeypatch.setattr(
        "backend.jobs.get_session",
        lambda _session_id: {
            "state": "working", "pr_url": "https://github.com/example/repo/pull/15",
            "messages": [], "structured_output": None,
        },
    )
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        calls.append((url, kwargs))
        return httpx.Response(200, json={"body": "No screenshots in this PR."})

    monkeypatch.setattr("backend.jobs.httpx.get", fake_get)
    job: dict[str, object] = {
        "stage": "devin_working", "timestamps": {}, "report": {"title": "Bug"},
        "devin_messages": [], "devin_state": None, "pr_url": None,
        "comparison": None, "comparison_status": None,
    }

    asyncio.run(_poll_session(job, "real-session", devin_vision=False))

    assert calls[0][0] == "https://api.github.com/repos/example/repo/pulls/15"
    assert calls[0][1]["headers"]["Authorization"] == "Bearer github-test"
    assert job["stage"] == "pr_opened"
    assert job["comparison_status"] == "unavailable"


def test_mock_pipeline_returns_pr(monkeypatch: pytest.MonkeyPatch, sample_video: Path) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("DEVIN_API_KEY", raising=False)
    monkeypatch.delenv("VISION_PROVIDER", raising=False)
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
        assert job["vision_provider"] == "mock"
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
        "structured_output": None,
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
        "structured_output": None,
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
        "structured_output": None,
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


def test_vision_provider_defaults_and_explicit_mock_rehearsal(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "VISION_PROVIDER",
        "DEVIN_API_KEY",
        "MOCK_DEVIN",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    assert select_vision_provider() == "mock"

    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-test")
    assert select_vision_provider() == "anthropic"
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test")
    assert select_vision_provider() == "openai"
    monkeypatch.setenv("DEVIN_API_KEY", "apk_test")
    assert select_vision_provider() == "devin"
    monkeypatch.setenv("MOCK_DEVIN", "1")
    assert select_vision_provider() == "openai"
    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert select_vision_provider() == "mock"

    monkeypatch.setenv("VISION_PROVIDER", "devin")
    assert select_vision_provider() == "devin"


def test_v1_upload_attachment_strips_response_quotes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DEVIN_API_KEY", "apk_legacy")
    monkeypatch.delenv("MOCK_DEVIN", raising=False)
    path = tmp_path / "frame.jpg"
    path.write_bytes(b"frame")
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        calls.append((url, kwargs))
        return httpx.Response(200, text='"https://devin.ai/attachments/frame.jpg"')

    monkeypatch.setattr("backend.devin.httpx.post", fake_post)

    assert upload_attachment(path) == "https://devin.ai/attachments/frame.jpg"
    assert calls[0][0] == "https://api.devin.ai/v1/attachments"
    file_info = calls[0][1]["files"]["file"]
    assert file_info[0] == "frame.jpg"
    assert file_info[2] == "image/jpeg"


def test_v3_upload_attachment_reads_url(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DEVIN_API_KEY", "cog_test")
    monkeypatch.setenv("DEVIN_ORG_ID", "org-test")
    monkeypatch.delenv("MOCK_DEVIN", raising=False)
    path = tmp_path / "frame.jpg"
    path.write_bytes(b"frame")
    calls: list[str] = []

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        calls.append(url)
        return httpx.Response(200, json={"url": "https://devin.ai/attachments/frame.jpg"})

    monkeypatch.setattr("backend.devin.httpx.post", fake_post)

    assert upload_attachment(path) == "https://devin.ai/attachments/frame.jpg"
    assert calls == ["https://api.devin.ai/v3/organizations/org-test/attachments"]


def test_v1_create_sends_schema_and_attachment_prompt_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVIN_API_KEY", "apk_test")
    monkeypatch.delenv("MOCK_DEVIN", raising=False)
    attachment_urls = ["https://devin.ai/frame-1.jpg", "https://devin.ai/frame-2.jpg"]
    schema = {"type": "object", "properties": {"title": {"type": "string"}}}
    prompt = build_vision_prompt("The subtotal is wrong.", attachment_urls)
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        calls.append((url, kwargs))
        return httpx.Response(200, json={"session_id": "session-v1", "url": "https://app.devin.ai/session-v1"})

    monkeypatch.setattr("backend.devin.httpx.post", fake_post)
    create_session(prompt, "Vision report", schema, attachment_urls)

    body = calls[0][1]["json"]
    prompt_lines = body["prompt"].splitlines()
    assert body["structured_output_schema"] == schema
    assert 'ATTACHMENT:"https://devin.ai/frame-1.jpg"' in prompt_lines
    assert 'ATTACHMENT:"https://devin.ai/frame-2.jpg"' in prompt_lines
    assert "attachment_urls" not in body
    assert "The subtotal is wrong." in body["prompt"]


def test_v3_create_sends_schema_and_attachment_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVIN_API_KEY", "cog_test")
    monkeypatch.setenv("DEVIN_ORG_ID", "org-test")
    monkeypatch.delenv("MOCK_DEVIN", raising=False)
    attachment_urls = ["https://devin.ai/frame-1.jpg"]
    schema = {"type": "object", "properties": {"title": {"type": "string"}}}
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        calls.append((url, kwargs))
        return httpx.Response(200, json={"session_id": "session-v3", "url": "https://app.devin.ai/session-v3"})

    monkeypatch.setattr("backend.devin.httpx.post", fake_post)
    create_session("Report from the video", "Ignored by v3", schema, attachment_urls)

    body = calls[0][1]["json"]
    assert body["structured_output_schema"] == schema
    assert body["attachment_urls"] == attachment_urls
    assert 'ATTACHMENT:"https://devin.ai/frame-1.jpg"' in body["prompt"].splitlines()
    assert "title" not in body


@pytest.mark.parametrize(
    ("structured_output", "expected"),
    [
        ({"title": "Concrete report"}, {"title": "Concrete report"}),
        ('{"title":"Concrete report"}', {"title": "Concrete report"}),
        ("not valid JSON", None),
        (["not", "an", "object"], None),
    ],
)
def test_v1_normalizes_structured_output(
    monkeypatch: pytest.MonkeyPatch,
    structured_output: object,
    expected: dict[str, object] | None,
) -> None:
    monkeypatch.setenv("DEVIN_API_KEY", "apk_legacy")
    monkeypatch.delenv("MOCK_DEVIN", raising=False)
    response = httpx.Response(
        200,
        json={"status_enum": "working", "structured_output": structured_output, "messages": []},
    )
    monkeypatch.setattr("backend.devin.httpx.get", lambda url, **kwargs: response)

    assert get_session("session-v1")["structured_output"] == expected


def test_devin_vision_mock_pipeline_uses_structured_report(
    monkeypatch: pytest.MonkeyPatch,
    sample_video: Path,
) -> None:
    monkeypatch.setenv("VISION_PROVIDER", "devin")
    monkeypatch.setenv("MOCK_DEVIN", "1")
    monkeypatch.setenv("MOCK_DEVIN_SECONDS", "0.5")
    monkeypatch.setenv("DEVIN_POLL_SECONDS", "0.05")
    monkeypatch.delenv("DEVIN_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    JOBS.clear()

    with TestClient(app) as client:
        with sample_video.open("rb") as video:
            response = client.post(
                "/api/reports",
                files={"video": ("recording.mp4", video, "video/mp4")},
                data={"note": "Two burgers should total $25.00."},
            )
        assert response.status_code == 200
        job_id = response.json()["job_id"]

        deadline = time.monotonic() + 10
        job = client.get(f"/api/reports/{job_id}").json()
        while job["stage"] not in {"pr_opened", "finished", "failed"} and time.monotonic() < deadline:
            time.sleep(0.05)
            job = client.get(f"/api/reports/{job_id}").json()

    assert job["stage"] == "pr_opened", job
    assert list(job["timestamps"]) == [
        "extracting",
        "analyzing",
        "dispatching",
        "devin_working",
        "pr_opened",
    ]
    assert job["report"]["title"] == "Tech Tower Burger quantity is omitted from the subtotal"
    assert "$12.50" in job["report"]["actual"]
    assert "$25.00" in job["report"]["expected"]
    assert job["vision_provider"] == "devin"
    assert job["pr_url"]
    assert job["comparison_status"] == "ready"
    assert job["comparison"]["before_url"] == "/mock/before.png"
    assert job["comparison"]["after_url"] == "/mock/after.png"
