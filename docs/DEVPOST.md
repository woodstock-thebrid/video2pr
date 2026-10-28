# Devpost submission (ready to paste)

**Project name:** video2pr

**Tagline:** Video in, PR out.

**Links**
- Repo: https://github.com/woodstock-thebrid/video2pr
- Demo video (real mode): https://github.com/woodstock-thebrid/video2pr/blob/main/docs/media/real_mode_demo.mp4
- Slides: https://github.com/woodstock-thebrid/video2pr/blob/main/docs/media/video2pr_slides.pdf
- Backup-mode GIF: https://github.com/woodstock-thebrid/video2pr/blob/main/docs/media/walkthrough.gif
- Real PRs opened by the pipeline: [#4](https://github.com/woodstock-thebrid/video2pr/pull/4) (multi-word search), [#8](https://github.com/woodstock-thebrid/video2pr/pull/8) (burger subtotal)

## Inspiration
Most bug reports are "it's broken." No steps, no expected vs. actual, no page. Engineers burn the first hour figuring out what the user saw. Everyone can record their screen in ten seconds, though. We wanted that recording to be the whole bug report, and the fix to come out the other end.

## What it does
We designed video2pr around a simple flow: video → key frames → structured report → reproduction → fix → reviewable PR with before/after proof. Upload a screen recording or press "Report a bug" inside the app; the AI agent writes the report, reproduces the bug in a real browser, fixes the code, and opens the PR. A human reviews and merges, while the page shows each stage live and multiple videos run in parallel.

## How we built it
- **FastAPI** backend with a small vanilla-JS frontend that polls job progress.
- **ffmpeg / ffprobe** sample up to 12 frames, including a WebM fallback when the recording has no container duration; an authenticated proxy serves screenshots.
- We built the job page, parallel job board, Video → PR timer, before/after comparison and lightbox, Real runs page, Markdown/GitHub issue actions, and in-app "Report a bug" recorder.
- The GT Dining demo app has four intentionally planted bugs; backup/mock mode supports rehearsals without API credits.
- We built the test suite, rehearsed real-mode runs, and produced the demo video and slides.
- We chose to send raw frames directly to the AI agent instead of adding a separate vision-model summary.
- **Devin API v1** provides frame attachments, one session per video, and structured output; the AI agent then reads the screenshots, reproduces the bug, fixes it, and opens a PR with before/after proof.

## Challenges we ran into
- Getting a reliable, structured bug report out of a few blurry phone frames.
- Browser MediaRecorder WebM files have no container duration, which broke frame sampling. We fall back to packet timestamps.
- Live demos are slow and flaky, so we built a mock mode that runs the full flow without API keys or credits.
- Shared GitHub access across teammates' accounts and organizations.

## Accomplishments that we're proud of
- A real end-to-end run from the in-app "Report a bug" button: bug report at **0:33**, PR opened at **1:24**, before/after on the page at about **1:56** ([PR #14](https://github.com/woodstock-thebrid/video2pr/pull/14)).
- An earlier rehearsal: bug report at about **0:33**, PR opened at about **1:35**, before/after on the page at about **2:30**.
- Real PRs opened by the pipeline: [#4](https://github.com/woodstock-thebrid/video2pr/pull/4) and [#8](https://github.com/woodstock-thebrid/video2pr/pull/8).
- One AI agent owns the whole loop, from reading the video to proving the fix. Nothing merges without human review.

## What we learned
- Giving the AI agent the raw screenshots works better than handing it a second model's summary, because no context is lost between handoffs.
- Before/after screenshots make an AI-written PR far easier to trust and review.
- Always have a backup mode for demos.

## What's next
- A drop-in "Report a bug" widget for any app.
- Auto-linking reports and PRs to GitHub issues.
