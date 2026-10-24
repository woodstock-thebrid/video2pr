import asyncio
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.devin import build_prompt, create_session, get_session
from backend.report import generate_report
from backend.video import extract_frames

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOADS_DIR = BASE_DIR / "uploads"
FRAMES_DIR = BASE_DIR / "frames"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
FRAMES_DIR.mkdir(parents=True, exist_ok=True)

JOBS: dict[str, dict[str, object]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _set_stage(job: dict[str, object], stage: str) -> None:
    job["stage"] = stage
    job["timestamps"][stage] = _now()


def create_job(upload_name: str, note: str | None = None) -> tuple[str, Path]:
    job_id = uuid.uuid4().hex
    safe_suffix = Path(upload_name).suffix.lower()[:12] or ".mp4"
    video_path = UPLOADS_DIR / f"{job_id}{safe_suffix}"
    JOBS[job_id] = {
        "job_id": job_id,
        "stage": "extracting",
        "timestamps": {"extracting": _now()},
        "frame_urls": [],
        "report": None,
        "devin_session_url": None,
        "pr_url": None,
        "devin_messages": [],
        "error": None,
        "note": note,
    }
    return job_id, video_path


async def run_pipeline(job_id: str, video_path: Path) -> None:
    job = JOBS[job_id]
    try:
        output_dir = FRAMES_DIR / job_id
        frames = await asyncio.to_thread(extract_frames, video_path, output_dir)
        job["frame_urls"] = [f"/frames/{job_id}/{frame.name}" for frame in frames]

        _set_stage(job, "analyzing")
        report = await asyncio.to_thread(generate_report, frames, job.get("note"))
        report_data = report.model_dump() if hasattr(report, "model_dump") else report.dict()
        job["report"] = report_data

        _set_stage(job, "dispatching")
        session = await asyncio.to_thread(create_session, build_prompt(report_data), report_data["title"])
        job["devin_session_url"] = session["url"]
        job["session_id"] = session["session_id"]
        _set_stage(job, "devin_working")

        poll_seconds = max(float(os.getenv("DEVIN_POLL_SECONDS", "10")), 0.05)
        while job["stage"] == "devin_working":
            session_data = await asyncio.to_thread(get_session, session["session_id"])
            job["devin_messages"] = (session_data.get("messages") or [])[-8:]
            pull_request = session_data.get("pull_request") or {}
            job["pr_url"] = pull_request.get("url") if isinstance(pull_request, dict) else None
            status = session_data.get("status_enum", "")
            if job["pr_url"]:
                _set_stage(job, "pr_opened")
                break
            if status in {"finished", "expired"}:
                _set_stage(job, "finished")
                break
            await asyncio.sleep(poll_seconds)
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
        "pr_url": job["pr_url"],
        "devin_messages": job["devin_messages"],
        "error": job["error"],
    }


def list_jobs() -> list[dict[str, object]]:
    return [get_job(job_id) for job_id in reversed(list(JOBS)) if get_job(job_id) is not None]
