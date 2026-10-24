import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from backend.devin import build_prompt, build_vision_prompt, create_session, get_session, upload_attachment
from backend.report import BugReport, generate_report, select_vision_provider
from backend.video import extract_frames

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOADS_DIR = BASE_DIR / "uploads"
FRAMES_DIR = BASE_DIR / "frames"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
FRAMES_DIR.mkdir(parents=True, exist_ok=True)

JOBS: dict[str, dict[str, object]] = {}


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


def create_job(upload_name: str, note: str | None = None) -> tuple[str, Path]:
    job_id = uuid.uuid4().hex
    vision_provider = select_vision_provider()
    safe_suffix = Path(upload_name).suffix.lower()[:12] or ".mp4"
    video_path = UPLOADS_DIR / f"{job_id}{safe_suffix}"
    JOBS[job_id] = {
        "job_id": job_id,
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
    }
    return job_id, video_path


async def _poll_session(job: dict[str, object], session_id: str, *, devin_vision: bool) -> None:
    poll_seconds = max(float(os.getenv("DEVIN_POLL_SECONDS", "10")), 0.05)
    while job["stage"] not in {"pr_opened", "finished", "failed"}:
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
            _set_stage(job, "pr_opened")
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
            schema_builder = getattr(BugReport, "model_json_schema", None)
            schema = schema_builder() if schema_builder else BugReport.schema()
            assert "$ref" not in json.dumps(schema), "BugReport schema must be self-contained"
            prompt = build_vision_prompt(job.get("note"), attachment_urls)
            session = await asyncio.to_thread(
                create_session,
                prompt,
                "Video bug investigation",
                schema,
                attachment_urls,
            )
        else:
            report = await asyncio.to_thread(generate_report, frames, job.get("note"))
            report_data = report.model_dump() if hasattr(report, "model_dump") else report.dict()
            job["report"] = report_data
            _set_stage(job, "dispatching")
            session = await asyncio.to_thread(create_session, build_prompt(report_data), report_data["title"])

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
    return {
        "job_id": job["job_id"],
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
    }


def list_jobs() -> list[dict[str, object]]:
    return [get_job(job_id) for job_id in reversed(list(JOBS)) if get_job(job_id) is not None]
