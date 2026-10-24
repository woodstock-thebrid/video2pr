import os
import time
import uuid
from datetime import datetime, timezone

import httpx

API_BASE = "https://api.devin.ai/v1"

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


def create_session(prompt: str, title: str) -> dict[str, str]:
    if _mock_enabled():
        session_id = f"mock-{uuid.uuid4().hex[:12]}"
        _mock_sessions[session_id] = {"created_at": time.monotonic(), "title": title, "messages": []}
        return {"session_id": session_id, "url": f"https://app.devin.ai/sessions/{session_id}"}

    response = httpx.post(
        f"{API_BASE}/sessions",
        headers={"Authorization": f"Bearer {os.environ['DEVIN_API_KEY']}"},
        json={"prompt": prompt, "title": title, "idempotent": False, "tags": ["video2pr"]},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    return {"session_id": data["session_id"], "url": data.get("url") or data.get("session_url", "")}


def get_session(session_id: str) -> dict[str, object]:
    if session_id.startswith("mock-"):
        session = _mock_sessions[session_id]
        elapsed = time.monotonic() - float(session["created_at"])
        duration = max(float(os.getenv("MOCK_DEVIN_SECONDS", "40")), 0.1)
        progress = min(elapsed / duration, 1)
        message_count = min(int(progress * len(_MOCK_MILESTONES)) + 1, len(_MOCK_MILESTONES))
        created = datetime.now(timezone.utc)
        messages = [
            {
                "message": message,
                "type": "status",
                "timestamp": created.isoformat(),
            }
            for message in _MOCK_MILESTONES[:message_count]
        ]
        return {
            "session_id": session_id,
            "status_enum": "finished" if progress >= 1 else "working",
            "pull_request": {
                "url": f"https://github.com/woodstock-thebrid/video2pr/pull/{int(session_id[-4:], 16) % 900 + 100}"
            }
            if progress >= 1
            else None,
            "messages": messages,
        }

    response = httpx.get(
        f"{API_BASE}/sessions/{session_id}",
        headers={"Authorization": f"Bearer {os.environ['DEVIN_API_KEY']}"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()
