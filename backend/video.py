import subprocess
from pathlib import Path


def _video_duration(video_path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        pass

    # Browser MediaRecorder WebM files carry no container duration; use the last packet timestamp.
    packets = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "packet=pts_time",
            "-of",
            "csv=p=0",
            str(video_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    timestamps = []
    for value in packets.stdout.split():
        try:
            timestamps.append(float(value.strip(",")))
        except ValueError:
            continue
    return max(timestamps, default=0.0)


def extract_frames(
    video_path: str | Path,
    out_dir: str | Path,
    fps: float = 1,
    max_frames: int = 12,
    width: int = 768,
) -> list[Path]:
    video_path = Path(video_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    duration = _video_duration(video_path)
    if duration <= 0 or fps <= 0 or max_frames <= 0:
        return []

    sample_fps = min(fps, max_frames / duration)
    output_pattern = out_dir / "frame-%03d.jpg"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video_path),
            "-vf",
            f"fps={sample_fps:.8f},scale={width}:-1",
            "-frames:v",
            str(max_frames),
            str(output_pattern),
        ],
        check=True,
        capture_output=True,
    )
    return sorted(out_dir.glob("frame-*.jpg"))
