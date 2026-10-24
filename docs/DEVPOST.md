# Devpost submission (ready to paste)

**Project name:** video2pr

**Tagline:** Video in, PR out.

**Links**
- Repo: https://github.com/woodstock-thebrid/video2pr
- Demo GIF: https://github.com/woodstock-thebrid/video2pr/blob/main/docs/media/walkthrough.gif
- Real PRs opened by the pipeline: [#4](https://github.com/woodstock-thebrid/video2pr/pull/4) (multi-word search), [#8](https://github.com/woodstock-thebrid/video2pr/pull/8) (burger subtotal)

## Inspiration
Most bug reports are "it's broken." No steps, no expected vs. actual, no page. Engineers burn the first hour figuring out what the user saw. Everyone can record their screen in ten seconds, though. We wanted that recording to be the whole bug report, and the fix to come out the other end.

## What it does
Upload a screen recording of a web-app bug, or press "Report a bug" inside the app. video2pr pulls key frames from the video, and Devin writes a structured bug report: title, page, steps, expected, actual, suspected area, severity. Devin then reproduces the bug in a real browser, fixes the code, and opens a pull request with before/after screenshots. The page shows each stage live, and multiple videos run as parallel investigations.

## How we built it
- **FastAPI** backend with a small vanilla-JS frontend that polls job progress.
- **ffmpeg / ffprobe** sample up to 12 frames from each video.
- **Devin API v1**:
  - **attachments**: we upload the frames.
  - **sessions**: one Devin session per video.
  - **structured output**: the session returns a typed bug report.
- Devin reads the screenshots itself, reproduces the bug in a browser, fixes it, and opens a PR with before/after screenshots. We show those screenshots and the diff on the job page.
- **Parallel sessions**: drop several videos and each one becomes its own Devin session.
- A demo app (GT Dining) with four bugs planted on purpose: math, mobile CSS, search logic, double submit.

## Challenges we ran into
- Getting a reliable, structured bug report out of a few blurry phone frames.
- Browser MediaRecorder WebM files have no container duration, which broke frame sampling. We fall back to packet timestamps.
- Live demos are slow and flaky, so we built a mock mode that runs the full flow without API keys or credits.
- Shared GitHub/Devin access across teammates' accounts and organizations.

## Accomplishments that we're proud of
- A real end-to-end run: bug report at about **0:33**, PR opened at about **1:35**, before/after on the page at about **2:30**.
- Real PRs opened by the pipeline: [#4](https://github.com/woodstock-thebrid/video2pr/pull/4) and [#8](https://github.com/woodstock-thebrid/video2pr/pull/8).
- One agent owns the whole loop, from watching the video to proving the fix. Nothing merges without human review.

## What we learned
- Giving the agent the raw screenshots works better than handing it a second model's summary, because no context is lost between handoffs.
- Before/after screenshots make an AI-written PR far easier to trust and review.
- Always have a backup mode for demos.

## What's next
- A drop-in "Report a bug" widget for any app.
- Auto-linking reports and PRs to GitHub issues.
