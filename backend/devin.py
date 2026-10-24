import os
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

API_BASE = "https://api.devin.ai"
DEFAULT_ORG_ID = "org-8df7501a85724235b32b5e64a28da839"

DEVIN_PROMPT_TEMPLATE = """Work in the repository {target_repo}.

## Bug report
Title: {title}
Page: {page}
Steps to reproduce:
{steps}
Expected: {expected}
Actual: {actual}
Suspected area: {suspected_area}
Severity: {severity}

Serve demo-app/ locally with `python3 -m http.server`, then reproduce the bug in a browser by following the steps above. Take a screenshot showing the bug. Make the minimal fix, then take another screenshot to verify the fix. Open a PR against `main` titled `Fix: {title}`. The PR description must include the bug report, the root cause in 1–2 sentences, and the before/after screenshots. Do not touch unrelated files."""

_mock_sessions: dict[str, dict[str, object]] = {}
_MOCK_MILESTONES = [
    "Session started; reviewing the bug report and repository.",
    "Running the demo app and following the reproduction steps.",
    "Found the relevant UI code; preparing a focused fix.",
    "Verifying the change and opening a pull request.",
]


def build_prompt(report: dict[str, object]) -> str:
    target_repo = os.getenv("TARGET_REPO", "woodstock-thebrid/video2pr")
    steps = "\n".join(f"{index}. {step}" for index, step in enumerate(report["steps"], start=1))
    return DEVIN_PROMPT_TEMPLATE.format(
        target_repo=target_repo,
        title=report["title"],
        page=report["page"],
        steps=steps,
        expected=report["expected"],
        actual=report["actual"],
        suspected_area=report["suspected_area"],
        severity=report["severity"],
    )


def _mock_enabled() -> bool:
    return not os.getenv("DEVIN_API_KEY") or os.getenv("MOCK_DEVIN") == "1"


def _api_version() -> str:
    return "v3" if os.getenv("DEVIN_API_KEY", "").startswith("cog_") else "v1"


def _org_base() -> str:
    org_id = os.getenv("DEVIN_ORG_ID", DEFAULT_ORG_ID)
    return f"/v3/organizations/{org_id}"


def _request(method: str, path: str, **kwargs: object) -> httpx.Response:
    response = getattr(httpx, method.lower())(f"{API_BASE}{path}", timeout=30, **kwargs)
    if not response.is_success:
        raise RuntimeError(f"{method} {path} -> {response.status_code}: {response.text[:300]}")
    return response


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {os.environ['DEVIN_API_KEY']}"}


def create_session(prompt: str, title: str) -> dict[str, str]:
    if _mock_enabled():
        session_id = f"mock-{uuid.uuid4().hex[:12]}"
        _mock_sessions[session_id] = {"created_at": time.monotonic(), "title": title}
        return {"session_id": session_id, "url": f"https://app.devin.ai/sessions/{session_id}"}

    if _api_version() == "v3":
        path = f"{_org_base()}/sessions"
        body = {
            "prompt": prompt,
            "tags": ["video2pr"],
            "repos": [os.getenv("TARGET_REPO", "woodstock-thebrid/video2pr")],
        }
    else:
        path = "/v1/sessions"
        body = {
            "prompt": prompt,
            "title": title,
            "idempotent": False,
            "tags": ["video2pr"],
        }
    data = _request("POST", path, headers=_headers(), json=body).json()
    return {"session_id": data["session_id"], "url": data.get("url") or data.get("session_url", "")}


def _messages(items: list[dict[str, object]], *, v3: bool) -> list[dict[str, object]]:
    if v3:
        return [
            {
                "message": item.get("message", ""),
                "source": item.get("source", ""),
                "timestamp": item.get("created_at"),
            }
            for item in items
        ]
    return [
        {
            "message": item.get("message", ""),
            "source": item.get("type", ""),
            "timestamp": item.get("timestamp"),
        }
        for item in items
    ]


def _v1_session(session_id: str) -> dict[str, object]:
    path = f"/v1/sessions/{quote(session_id, safe='')}"
    data = _request("GET", path, headers=_headers()).json()
    status = str(data.get("status_enum", "unknown"))
    normalized = status.lower()
    if normalized == "blocked":
        state = "waiting_for_user"
    elif normalized == "finished":
        state = "finished"
    elif normalized == "expired":
        state = "failed"
    else:
        state = "working"
    pull_request = data.get("pull_request") or {}
    return {
        "state": state,
        "pr_url": pull_request.get("url") if isinstance(pull_request, dict) else None,
        "messages": _messages(data.get("messages") or [], v3=False),
        "raw_status": status,
    }


def _v3_session(session_id: str) -> dict[str, object]:
    encoded_id = quote(session_id, safe="")
    path = f"{_org_base()}/sessions/{encoded_id}"
    data = _request("GET", path, headers=_headers()).json()
    status = str(data.get("status", "unknown"))
    detail = str(data.get("status_detail") or "")
    normalized = status.lower()
    normalized_detail = detail.lower()
    if normalized == "running" and normalized_detail == "finished":
        state = "finished"
    elif normalized == "running" and normalized_detail in {"waiting_for_user", "waiting_for_approval"}:
        state = "waiting_for_user"
    elif normalized == "exit":
        state = "finished"
    elif normalized in {"error", "suspended"}:
        state = "failed"
    else:
        state = "working"

    message_path = f"{path}/messages?first=100"
    message_data = _request("GET", message_path, headers=_headers()).json()
    pull_requests = data.get("pull_requests") or []
    first_pull_request = next((item for item in pull_requests if item.get("pr_url")), None)
    return {
        "state": state,
        "pr_url": first_pull_request.get("pr_url") if first_pull_request else None,
        "messages": _messages(message_data.get("items") or [], v3=True),
        "raw_status": f"{status}:{detail}" if detail else status,
    }


def get_session(session_id: str) -> dict[str, object]:
    if session_id.startswith("mock-"):
        session = _mock_sessions[session_id]
        elapsed = time.monotonic() - float(session["created_at"])
        duration = max(float(os.getenv("MOCK_DEVIN_SECONDS", "40")), 0.1)
        progress = min(elapsed / duration, 1)
        message_count = min(int(progress * len(_MOCK_MILESTONES)) + 1, len(_MOCK_MILESTONES))
        timestamp = datetime.now(timezone.utc).isoformat()
        finished = progress >= 1
        return {
            "state": "finished" if finished else "working",
            "pr_url": f"https://github.com/woodstock-thebrid/video2pr/pull/{int(session_id[-4:], 16) % 900 + 100}"
            if finished
            else None,
            "messages": [
                {"message": message, "source": "devin", "timestamp": timestamp}
                for message in _MOCK_MILESTONES[:message_count]
            ],
            "raw_status": "finished" if finished else "working",
        }

    if _api_version() == "v3":
        return _v3_session(session_id)
    return _v1_session(session_id)
