import asyncio
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.jobs import FRAMES_DIR, create_job, get_job, list_jobs, run_pipeline

BASE_DIR = Path(__file__).resolve().parent.parent
FRAMES_DIR.mkdir(parents=True, exist_ok=True)
load_dotenv(BASE_DIR / ".env")

app = FastAPI(title="video2pr")
_BATCH_PIPELINE_TASKS: set[asyncio.Task[None]] = set()


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


@app.api_route("/demo", methods=["GET", "HEAD"], include_in_schema=False)
async def demo_redirect() -> RedirectResponse:
    return RedirectResponse("/demo/")


app.mount("/frames", StaticFiles(directory=FRAMES_DIR), name="frames")
app.mount("/demo", StaticFiles(directory=BASE_DIR / "demo-app", html=True), name="demo")
app.mount("/", StaticFiles(directory=BASE_DIR / "frontend", html=True), name="frontend")
