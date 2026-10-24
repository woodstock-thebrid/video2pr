import asyncio
import os
import re
import uuid
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.devin import API_BASE
from backend.jobs import FRAMES_DIR, create_job, get_job, list_jobs, run_pipeline

BASE_DIR = Path(__file__).resolve().parent.parent
FRAMES_DIR.mkdir(parents=True, exist_ok=True)
load_dotenv(BASE_DIR / ".env")

app = FastAPI(title="video2pr")
_BATCH_PIPELINE_TASKS: set[asyncio.Task[None]] = set()
_COMPARISON_ATTACHMENT_URL = re.compile(
    r"^https://app\.devin\.ai/attachments/([^/]+)/([^/?#]+)$"
)
_COMPARISON_IMAGE_CACHE: dict[tuple[str, str], tuple[bytes, str]] = {}


@app.post("/api/reports")
async def create_report(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    note: str | None = Form(default=None),
) -> dict[str, str]:
    if not video.filename:
        raise HTTPException(status_code=400, detail="A video filename is required.")
    job_id, video_path = create_job(video.filename, note)
    video_path.write_bytes(await video.read())
    background_tasks.add_task(run_pipeline, job_id, video_path)
    return {"job_id": job_id}


@app.post("/api/reports/batch")
async def create_batch_reports(
    videos: list[UploadFile] = File(...),
    note: str | None = Form(default=None),
) -> dict[str, object]:
    try:
        max_batch = int(os.getenv("MAX_BATCH_VIDEOS", "4"))
    except ValueError:
        max_batch = 4
    if max_batch < 1:
        max_batch = 4
    if not videos:
        raise HTTPException(status_code=400, detail="Upload at least one video.")
    if len(videos) > max_batch:
        raise HTTPException(
            status_code=400,
            detail=f"Too many videos. Upload between 1 and {max_batch} videos.",
        )
    if any(not video.filename for video in videos):
        raise HTTPException(status_code=400, detail="Every uploaded video needs a filename.")

    batch_id = uuid.uuid4().hex
    batch_jobs: list[tuple[str, Path]] = []
    for video in videos:
        job_id, video_path = create_job(video.filename, note, batch_id=batch_id)
        video_path.write_bytes(await video.read())
        batch_jobs.append((job_id, video_path))

    for job_id, video_path in batch_jobs:
        task = asyncio.create_task(run_pipeline(job_id, video_path))
        _BATCH_PIPELINE_TASKS.add(task)
        task.add_done_callback(_BATCH_PIPELINE_TASKS.discard)

    return {"batch_id": batch_id, "job_ids": [job_id for job_id, _ in batch_jobs]}


@app.get("/api/reports")
async def reports() -> list[dict[str, object]]:
    return list_jobs()


@app.get("/api/reports/{job_id}")
async def report_status(job_id: str) -> dict[str, object]:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@app.get("/api/reports/{job_id}/comparison/{which}")
async def comparison_image(job_id: str, which: str) -> Response:
    if which not in {"before", "after"}:
        raise HTTPException(status_code=404, detail="Comparison image not found.")
    job = get_job(job_id)
    comparison = job.get("comparison") if job else None
    if not isinstance(comparison, dict) or job.get("comparison_status") != "ready":
        raise HTTPException(status_code=404, detail="Comparison image not found.")
    source_url = comparison.get(f"{which}_url")
    if not isinstance(source_url, str):
        raise HTTPException(status_code=404, detail="Comparison image not found.")

    cache_key = (job_id, which)
    cached = _COMPARISON_IMAGE_CACHE.get(cache_key)
    if cached is not None:
        content, content_type = cached
        return Response(
            content=content,
            headers={"Content-Type": content_type, "Cache-Control": "max-age=3600"},
        )

    attachment = _COMPARISON_ATTACHMENT_URL.fullmatch(source_url)
    if attachment:
        api_key = os.getenv("DEVIN_API_KEY")
        if not api_key:
            raise HTTPException(status_code=502, detail="Unable to fetch Devin comparison image.")
        attachment_id, filename = attachment.groups()
        upstream_url = (
            f"{API_BASE}/v1/attachments/{quote(attachment_id, safe='')}/"
            f"{quote(filename, safe='')}"
        )
        try:
            upstream = await asyncio.to_thread(
                httpx.get,
                upstream_url,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=30,
            )
        except Exception as error:
            raise HTTPException(
                status_code=502,
                detail="Unable to fetch Devin comparison image.",
            ) from error
        if not upstream.is_success:
            raise HTTPException(status_code=502, detail="Unable to fetch Devin comparison image.")
        content_type = upstream.headers.get("content-type", "application/octet-stream")
        content = upstream.content
        _COMPARISON_IMAGE_CACHE[cache_key] = (content, content_type)
        return Response(
            content=content,
            headers={"Content-Type": content_type, "Cache-Control": "max-age=3600"},
        )

    parsed_url = urlparse(source_url)
    is_http_url = parsed_url.scheme.lower() in {"http", "https"} and bool(parsed_url.netloc)
    is_relative_url = source_url.startswith("/") and not source_url.startswith("//")
    if is_http_url or is_relative_url:
        return RedirectResponse(source_url, status_code=307)
    raise HTTPException(status_code=404, detail="Comparison image not found.")


@app.api_route("/demo", methods=["GET", "HEAD"], include_in_schema=False)
async def demo_redirect() -> RedirectResponse:
    return RedirectResponse("/demo/")


app.mount("/frames", StaticFiles(directory=FRAMES_DIR), name="frames")
app.mount("/demo", StaticFiles(directory=BASE_DIR / "demo-app", html=True), name="demo")
app.mount("/", StaticFiles(directory=BASE_DIR / "frontend", html=True), name="frontend")
