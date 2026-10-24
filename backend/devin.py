import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import httpx

from backend.report import BugReport

API_BASE = "https://api.devin.ai"
DEFAULT_ORG_ID = "org-8df7501a85724235b32b5e64a28da839"

DEVIN_FIX_INSTRUCTIONS = """Serve demo-app/ locally with `python3 -m http.server`, then reproduce the bug in a browser by following the steps above. Take a screenshot showing the bug. Make the minimal fix, then take another screenshot to verify the fix. Open a PR against `main` titled `Fix: {title}`. The PR description must include the bug report, the root cause in 1–2 sentences, and the before/after screenshots. In the PR body, label the images with alt text exactly `before` and `after`. After opening the PR, update the structured output again with all bug report fields plus `before_screenshot_url` and `after_screenshot_url` (the exact URLs of the before and after screenshots embedded in the PR), `root_cause` (1–2 sentences), and `code_diff` (the unified diff of your fix). Do not touch unrelated files."""

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

{fix_instructions}"""

_mock_sessions: dict[str, dict[str, object]] = {}
_MOCK_MILESTONES = [
    "Session started; reviewing the bug report and repository.",
    "Running the demo app and following the reproduction steps.",
    "Found the relevant UI code; preparing a focused fix.",
    "Verifying the change and opening a pull request.",
]
_MOCK_VISION_REPORT = {
    "title": "Tech Tower Burger quantity is omitted from the subtotal",
    "page": "GT Dining order page",
    "steps": [
        "Open GT Dining and add one Tech Tower Burger.",
        "Click the plus control once so the cart quantity is 2.",
    ],
    "expected": "The subtotal should be $25.00 for two Tech Tower Burgers at $12.50 each.",
    "actual": "The cart shows quantity 2, but the subtotal is $12.50.",
    "suspected_area": "The burger subtotal calculation in demo-app/app.js does not multiply by quantity.",
    "severity": "medium",
}


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
        fix_instructions=DEVIN_FIX_INSTRUCTIONS.format(title=report["title"]),
    )


def build_session_schema() -> dict[str, object]:
    schema_builder = getattr(BugReport, "model_json_schema", None)
    schema = schema_builder() if schema_builder else BugReport.schema()
    properties = schema.setdefault("properties", {})
    properties.update(
        {
            "before_screenshot_url": {
                "type": "string",
                "description": "Exact URL of the before screenshot embedded in the PR.",
            },
            "after_screenshot_url": {
                "type": "string",
                "description": "Exact URL of the after screenshot embedded in the PR.",
            },
            "root_cause": {
                "type": "string",
                "description": "One or two sentences describing the root cause.",
            },
            "code_diff": {
                "type": "string",
                "description": "Unified diff of the minimal fix.",
            },
        }
    )
    assert "$ref" not in json.dumps(schema), "Session schema must be self-contained"
    return schema


def build_vision_prompt(note: str | None, attachment_urls: list[str]) -> str:
    target_repo = os.getenv("TARGET_REPO", "woodstock-thebrid/video2pr")
    note_text = note.strip() if note and note.strip() else "No optional note was provided."
    attachment_lines = "\n".join(f'ATTACHMENT:"{url}"' for url in attachment_urls)
    fix_instructions = DEVIN_FIX_INSTRUCTIONS.format(title="the title from the structured bug report")
    prompt = f"""Work in the repository {target_repo}.

The attached images are frames sampled at 1 fps, in order, from a screen recording of a bug in the web app in `demo-app/` (GT Dining).

User note (context for the bug report):
{note_text}

Step 1: Study every frame and write a complete bug report. Immediately submit it as structured output with the fields title, page, steps, expected, actual, suspected_area, and severity BEFORE reproducing the bug or changing files. Be concrete: name the menu items and controls visible in the frames and include exact dollar amounts shown.

Step 2 onward: After submitting the structured bug report, follow these instructions:
{fix_instructions}

{attachment_lines}"""
    return prompt.rstrip()


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


def upload_attachment(path: Path) -> str:
    if _mock_enabled():
        return f"https://mock.devin.ai/attachments/{quote(path.name)}"

    with path.open("rb") as attachment:
        files = {"file": (path.name, attachment, "image/jpeg")}
        if _api_version() == "v3":
            response = _request("POST", f"{_org_base()}/attachments", headers=_headers(), files=files)
            url = response.json().get("url")
            if not isinstance(url, str):
                raise RuntimeError("Devin attachment response did not include a URL.")
            return url
        response = _request("POST", "/v1/attachments", headers=_headers(), files=files)

    try:
        value = response.json()
    except ValueError:
        value = response.text
    if isinstance(value, str):
        return value.strip().strip('"')
    if isinstance(value, dict) and isinstance(value.get("url"), str):
        return value["url"]
    raise RuntimeError("Devin attachment response did not include a URL.")


def _with_attachment_lines(prompt: str, attachment_urls: list[str] | None) -> str:
    lines = [f'ATTACHMENT:"{url}"' for url in attachment_urls or []]
    existing = set(prompt.splitlines())
    missing = [line for line in lines if line not in existing]
    return f"{prompt.rstrip()}\n\n{chr(10).join(missing)}" if missing else prompt


def create_session(
    prompt: str,
    title: str,
    structured_output_schema: dict[str, object] | None = None,
    attachment_urls: list[str] | None = None,
) -> dict[str, str]:
    if _mock_enabled():
        session_id = f"mock-{uuid.uuid4().hex[:12]}"
        _mock_sessions[session_id] = {
            "created_at": time.monotonic(),
            "title": title,
            "structured_output_enabled": structured_output_schema is not None,
        }
        return {"session_id": session_id, "url": f"https://app.devin.ai/sessions/{session_id}"}

    prompt = _with_attachment_lines(prompt, attachment_urls)
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
    if structured_output_schema is not None:
        body["structured_output_schema"] = structured_output_schema
    if _api_version() == "v3" and attachment_urls:
        body["attachment_urls"] = attachment_urls
    data = _request("POST", path, headers=_headers(), json=body).json()
    return {"session_id": data["session_id"], "url": data.get("url") or data.get("session_url", "")}


def _normalize_structured_output(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


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
        "structured_output": _normalize_structured_output(data.get("structured_output")),
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
        "structured_output": _normalize_structured_output(data.get("structured_output")),
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
        structured_output = (
            {
                **_MOCK_VISION_REPORT,
                **(
                    {
                        "before_screenshot_url": "/mock/before.png",
                        "after_screenshot_url": "/mock/after.png",
                        "root_cause": (
                            "The burger subtotal calculation omitted the quantity when computing "
                            "the line total."
                        ),
                        "code_diff": (
                            '-    return sum + item.price * (id === "burger" ? 1 : quantity);\n'
                            '+    return sum + item.price * quantity;'
                        ),
                    }
                    if finished
                    else {}
                ),
            }
            if session.get("structured_output_enabled") and progress >= 0.2
            else None
        )
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
            "structured_output": structured_output,
        }

    if _api_version() == "v3":
        return _v3_session(session_id)
    return _v1_session(session_id)
