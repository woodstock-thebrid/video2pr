import asyncio
import html
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pydantic import ValidationError

from backend.devin import (
    build_prompt,
    build_session_schema,
    build_vision_prompt,
    create_session,
    get_session,
    upload_attachment,
)
from backend.report import BugReport, generate_report, select_vision_provider
from backend.video import extract_frames

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOADS_DIR = BASE_DIR / "uploads"
FRAMES_DIR = BASE_DIR / "frames"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
FRAMES_DIR.mkdir(parents=True, exist_ok=True)

JOBS: dict[str, dict[str, object]] = {}

_IMAGE_MARKDOWN_OR_HTML = re.compile(
    r"!\[(?P<markdown_alt>[^\]]*)\]\(\s*(?P<markdown_url><[^>]+>|[^)\s]+)"
    r"(?:\s+['\"][^)]*['\"])?\s*\)|<img\b(?P<html_attributes>[^>]*)>",
    re.IGNORECASE,
)
_HTML_ATTRIBUTE = re.compile(
    r"(?P<name>[^\s=/>]+)\s*=\s*(?:\"(?P<double>[^\"]*)\"|'(?P<single>[^']*)'|(?P<bare>[^\s>]+))"
)


def _validated_report(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    try:
        validator = getattr(BugReport, "model_validate", None)
        report = validator(value) if validator else BugReport.parse_obj(value)
    except (ValidationError, TypeError, ValueError):
        return None
    return report.model_dump() if hasattr(report, "model_dump") else report.dict()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _set_stage(job: dict[str, object], stage: str) -> None:
    job["stage"] = stage
    job["timestamps"][stage] = _now()


def extract_before_after(markdown: str) -> tuple[str | None, str | None]:
    images: list[tuple[str, str]] = []
    for match in _IMAGE_MARKDOWN_OR_HTML.finditer(markdown):
        markdown_url = match.group("markdown_url")
        if markdown_url is not None:
            alt = match.group("markdown_alt") or ""
            url = markdown_url.strip().strip("<>")
        else:
            attributes: dict[str, str] = {}
            for attribute in _HTML_ATTRIBUTE.finditer(match.group("html_attributes") or ""):
                value = next(
                    (
                        attribute.group(group_name)
                        for group_name in ("double", "single", "bare")
                        if attribute.group(group_name) is not None
                    ),
                    "",
                )
                attributes[attribute.group("name").lower()] = value
            alt = attributes.get("alt", "")
            url = attributes.get("src", "")
        alt = html.unescape(alt)
        url = html.unescape(url).strip()
        if url:
            images.append((alt, url))

    before = next((url for alt, url in images if "before" in alt.lower()), None)
    after = next((url for alt, url in images if "after" in alt.lower()), None)
    if before and after and before != after:
        return before, after
    if len(images) >= 2:
        return images[0][1], images[1][1]
    return None, None


def _valid_comparison_url(value: object, *, allow_relative: bool) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    url = value.strip()
    parsed = urlparse(url)
    if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
        return True
    return allow_relative and url.startswith("/") and not url.startswith("//")


def _comparison_from_structured_output(
    value: object,
    *,
    allow_relative: bool,
) -> dict[str, str | None] | None:
    if not isinstance(value, dict):
        return None
    before_url = value.get("before_screenshot_url")
    after_url = value.get("after_screenshot_url")
    if not _valid_comparison_url(before_url, allow_relative=allow_relative):
        return None
    if not _valid_comparison_url(after_url, allow_relative=allow_relative):
        return None
    root_cause = value.get("root_cause")
    code_diff = value.get("code_diff")
    return {
        "before_url": before_url.strip(),
        "after_url": after_url.strip(),
        "root_cause": root_cause if isinstance(root_cause, str) else None,
        "code_diff": code_diff if isinstance(code_diff, str) else None,
    }


def _pull_request_api_url(pr_url: str) -> str | None:
    parsed = urlparse(pr_url)
    if parsed.hostname != "github.com":
        return None
    parts = parsed.path.strip("/").split("/")
    if len(parts) != 4 or parts[2].lower() != "pull" or not parts[3].isdigit():
        return None
    owner, repository = parts[0], parts[1].removesuffix(".git")
    if not owner or not repository:
        return None
    return f"https://api.github.com/repos/{owner}/{repository}/pulls/{parts[3]}"


def _pull_request_body(pr_url: str) -> str | None:
    api_url = _pull_request_api_url(pr_url)
    if api_url is None:
        return None
    headers = {"Accept": "application/vnd.github+json"}
    github_token = os.getenv("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
    try:
        response = httpx.get(api_url, headers=headers, timeout=10)
        if not response.is_success:
            return None
        body = response.json().get("body")
        return body if isinstance(body, str) else None
    except Exception:
        return None


async def _fallback_comparison(job: dict[str, object]) -> None:
    pr_url = job.get("pr_url")
    body = await asyncio.to_thread(_pull_request_body, str(pr_url)) if pr_url else None
    before_url, after_url = extract_before_after(body or "")
    if before_url and after_url:
        job["comparison"] = {
            "before_url": before_url,
            "after_url": after_url,
            "root_cause": None,
            "code_diff": None,
        }
        job["comparison_status"] = "ready"
    else:
        job["comparison_status"] = "unavailable"


def create_job(
    upload_name: str,
    note: str | None = None,
    *,
    batch_id: str | None = None,
) -> tuple[str, Path]:
    job_id = uuid.uuid4().hex
    vision_provider = select_vision_provider()
    safe_suffix = Path(upload_name).suffix.lower()[:12] or ".mp4"
    video_path = UPLOADS_DIR / f"{job_id}{safe_suffix}"
    JOBS[job_id] = {
        "job_id": job_id,
        "upload_name": upload_name,
        "batch_id": batch_id,
        "stage": "extracting",
        "timestamps": {"extracting": _now()},
        "frame_urls": [],
        "report": None,
        "devin_session_url": None,
        "devin_state": None,
        "pr_url": None,
        "devin_messages": [],
        "error": None,
        "note": note,
        "vision_provider": vision_provider,
        "comparison": None,
        "comparison_status": None,
    }
    return job_id, video_path


async def _poll_session(job: dict[str, object], session_id: str, *, devin_vision: bool) -> None:
    poll_seconds = max(float(os.getenv("DEVIN_POLL_SECONDS", "10")), 0.05)
    comparison_timeout = max(float(os.getenv("COMPARISON_TIMEOUT_SECONDS", "600")), 0)
    pr_opened_at: float | None = None
    while True:
        session_data = await asyncio.to_thread(get_session, session_id)
        job["devin_messages"] = (session_data.get("messages") or [])[-8:]
        job["devin_state"] = session_data.get("state", "working")
        job["pr_url"] = session_data.get("pr_url")

        if devin_vision and job["report"] is None:
            report_data = _validated_report(session_data.get("structured_output"))
            if report_data is not None:
                job["report"] = report_data
                _set_stage(job, "dispatching")
                _set_stage(job, "devin_working")

        if job["pr_url"]:
            if job["stage"] != "pr_opened":
                _set_stage(job, "pr_opened")
                job["comparison_status"] = "waiting"
                pr_opened_at = time.monotonic()
            comparison = _comparison_from_structured_output(
                session_data.get("structured_output"),
                allow_relative=session_id.startswith("mock-"),
            )
            if comparison is not None:
                job["comparison"] = comparison
                job["comparison_status"] = "ready"
                break
            if job["devin_state"] in {"finished", "failed"}:
                await _fallback_comparison(job)
                break
            if pr_opened_at is not None and time.monotonic() - pr_opened_at >= comparison_timeout:
                await _fallback_comparison(job)
                break
        if job["devin_state"] == "finished":
            if devin_vision and job["report"] is None:
                final_report = _validated_report(session_data.get("structured_output"))
                if final_report is not None:
                    job["report"] = final_report
            _set_stage(job, "finished")
            break
        if job["devin_state"] == "failed":
            job["error"] = f"Devin session {session_data.get('raw_status', 'failed')}"
            _set_stage(job, "failed")
            break
        await asyncio.sleep(poll_seconds)


async def run_pipeline(job_id: str, video_path: Path) -> None:
    job = JOBS[job_id]
    try:
        output_dir = FRAMES_DIR / job_id
        frames = await asyncio.to_thread(extract_frames, video_path, output_dir)
        job["frame_urls"] = [f"/frames/{job_id}/{frame.name}" for frame in frames]

        _set_stage(job, "analyzing")
        devin_vision = job["vision_provider"] == "devin"
        if devin_vision:
            attachment_urls = []
            for frame in frames:
                attachment_urls.append(await asyncio.to_thread(upload_attachment, frame))
            schema = build_session_schema()
            prompt = build_vision_prompt(job.get("note"), attachment_urls)
            session = await asyncio.to_thread(
                create_session,
                prompt,
                "Video bug investigation",
                schema,
                attachment_urls,
                upload_name=str(job["upload_name"]),
            )
        else:
            report = await asyncio.to_thread(
                generate_report,
                frames,
                job.get("note"),
                str(job["upload_name"]),
            )
            report_data = report.model_dump() if hasattr(report, "model_dump") else report.dict()
            job["report"] = report_data
            _set_stage(job, "dispatching")
            session = await asyncio.to_thread(
                create_session,
                build_prompt(report_data),
                report_data["title"],
                build_session_schema(),
                upload_name=str(job["upload_name"]),
            )

        job["devin_session_url"] = session["url"]
        job["session_id"] = session["session_id"]
        if not devin_vision:
            _set_stage(job, "devin_working")
        await _poll_session(job, session["session_id"], devin_vision=devin_vision)
    except Exception as exc:
        job["error"] = str(exc)
        _set_stage(job, "failed")
    finally:
        if video_path.exists():
            video_path.unlink()


def get_job(job_id: str) -> dict[str, object] | None:
    job = JOBS.get(job_id)
    if job is None:
        return None
    comparison = job["comparison"]
    comparison_with_sources = None
    if isinstance(comparison, dict):
        comparison_with_sources = {
            **comparison,
            "before_src": f"/api/reports/{job_id}/comparison/before",
            "after_src": f"/api/reports/{job_id}/comparison/after",
        }
    return {
        "job_id": job["job_id"],
        "upload_name": job["upload_name"],
        "batch_id": job["batch_id"],
        "stage": job["stage"],
        "timestamps": job["timestamps"],
        "frame_urls": job["frame_urls"],
        "report": job["report"],
        "devin_session_url": job["devin_session_url"],
        "devin_state": job["devin_state"],
        "pr_url": job["pr_url"],
        "devin_messages": job["devin_messages"],
        "error": job["error"],
        "vision_provider": job["vision_provider"],
        "comparison": comparison_with_sources,
        "comparison_status": job["comparison_status"],
    }


def list_jobs() -> list[dict[str, object]]:
    return [get_job(job_id) for job_id in reversed(list(JOBS)) if get_job(job_id) is not None]
