# video2pr

We designed video2pr to turn a phone screen recording of a web-app bug into key frames and a structured report. The AI agent reads the frames, reproduces and fixes the issue, then opens a pull request with before/after proof for a human to review and merge.

## What we built
- Designed the video → key frames → structured report → reproduce → fix → PR workflow, with before/after proof and human review.
- Built the FastAPI backend and vanilla-JS job page, ffmpeg frame sampling (including a WebM no-duration fallback), and authenticated screenshot proxy.
- Added the parallel job board, Video → PR timer, before/after comparison and lightbox, Real runs page, Markdown/GitHub issue actions, and in-app Report a bug recorder.
- Built GT Dining with four planted bugs, backup/mock mode, the test suite, real-mode rehearsals, and the demo video and slides.
- Chose to send raw key frames straight to the AI agent rather than add a separate vision-model summary.

We used an AI coding assistant to write much of the implementation. The team owned the idea, design decisions, task split, code review, and the demo.

![video2pr real-mode demo: click "Report a bug" in the demo app, the AI agent writes the report, opens a PR in 1m 18s, before/after comparison](docs/media/real_mode_demo.gif)

<sub>Real AI-agent run, waiting parts sped up. Full video: [`docs/media/real_mode_demo.mp4`](docs/media/real_mode_demo.mp4) (resulting PR: #17, intentionally unmerged). Slides: [`docs/media/video2pr_slides.pptx`](docs/media/video2pr_slides.pptx) / [PDF](docs/media/video2pr_slides.pdf).</sub>

### Backup mode

![video2pr backup-mode walkthrough: upload a bug video, get a bug report, a PR, and a before/after comparison](docs/media/walkthrough.gif)

<sub>Backup (mock) mode, sped up 2x. Full-speed recording: [`docs/media/backup_mode_walkthrough.mp4`](docs/media/backup_mode_walkthrough.mp4). Final screen: [`docs/media/walkthrough_result.png`](docs/media/walkthrough_result.png).</sub>

## Architecture

```text
Phone/browser video
        │
        ▼
FastAPI upload ──► ffprobe + ffmpeg frame extraction
        │
        ▼
Vision report (AI agent structured output / OpenAI / Anthropic / local mock)
        │
        ▼
AI agent API session (or simulated session)
        │
        ├──► Static frontend: progress, frames, report, messages, PR
        └──► /demo/: GT Dining ordering app for the repro walkthrough
```

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn backend.main:app --reload --port 8000
```

The frontend is available at <http://localhost:8000>, and the sample GT Dining app is at <http://localhost:8000/demo/>.

Set `VISION_PROVIDER` to `devin`, `openai`, `anthropic`, or `mock` to choose the vision provider explicitly. When unset, a live AI-agent key is preferred, followed by OpenAI, Anthropic, then the local mock. With `VISION_PROVIDER=devin`, the ordered video frames go straight to the AI agent for a structured bug report before it reproduces the issue. Set `VISION_PROVIDER=devin` with `MOCK_DEVIN=1` to rehearse that flow without creating a real session.

Without provider keys, video reports use a mock report and AI-agent sessions run in simulation mode. Add `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` for external vision analysis. Add `DEVIN_API_KEY` to create real AI-agent sessions. `DEVIN_ORG_ID` selects the organization for `cog_` personal access tokens, and `MOCK_DEVIN=1` forces session simulation. The simulated session takes about 40 seconds by default; set `MOCK_DEVIN_SECONDS` to change that duration. Agent sessions use the Devin API v1 for legacy tokens and v3 for `cog_` personal access tokens (attachments, sessions, structured output).

Select multiple recordings to start parallel investigations. `POST /api/reports/batch` accepts 1 to `MAX_BATCH_VIDEOS` files (default 4) and an optional note shared across the batch.

`run.sh` starts the same development server.
