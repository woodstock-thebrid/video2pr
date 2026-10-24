from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles

from backend.jobs import FRAMES_DIR, create_job, get_job, list_jobs, run_pipeline

BASE_DIR = Path(__file__).resolve().parent.parent
FRAMES_DIR.mkdir(parents=True, exist_ok=True)
load_dotenv(BASE_DIR / ".env")

app = FastAPI(title="video2pr")


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


@app.get("/api/reports")
async def reports() -> list[dict[str, object]]:
    return list_jobs()


@app.get("/api/reports/{job_id}")
async def report_status(job_id: str) -> dict[str, object]:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


app.mount("/frames", StaticFiles(directory=FRAMES_DIR), name="frames")
app.mount("/demo", StaticFiles(directory=BASE_DIR / "demo-app", html=True), name="demo")
app.mount("/", StaticFiles(directory=BASE_DIR / "frontend", html=True), name="frontend")
