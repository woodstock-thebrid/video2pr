# video2pr: Pitch & 3-Minute Demo Script

**One-liner:** *Video in, PR out.* Record a bug. Devin watches it, writes the bug report, fixes the code, and opens a pull request. No one has to write a ticket.

---

## Before you go on stage (checklist)
- Tab 1: **video2pr, real mode** (preview link). Leave the page open on the upload screen.
- Tab 2: **GT Dining demo app** (`/demo/`) at a browser width where the bug is obvious.
- Tab 3: **Backup PR**: [PR #4](https://github.com/woodstock-thebrid/video2pr/pull/4) (search bug, fixed from video only, no text hint).
- Tab 4: **Mock mode** (backup preview link) in case Wi-Fi or Devin is slow.
- Phone: screen recording ready, or use the pre-recorded `docs/media/bug1_quantity.mp4` / `docs/media/bug4_double_order.mp4`.
- Live bug to use: **bug 1 (burger quantity)** or **bug 4 (double order)**. Bugs 2/3 already have PRs, so use them as backups.
- **Never merge the fix PRs** (#2, #4, and any new ones). Merging removes the planted bugs.

---

## Script (≈3:00)

### 0:00–0:25: Hook (Speaker A)
> "Raise your hand if you've ever gotten a bug report that just said *'it's broken.'*
> Users, PMs, customers: they can't write a good bug report. But everyone can record their screen.
> So we asked: what if a screen recording **was** the bug report, and the fix?"

### 0:25–0:50: Live recording (Speaker B, while A narrates)
- Open GT Dining. Add a **Tech Tower Burger**, click **+** so the quantity is 2.
- Point at the subtotal: **$12.50 instead of $25.00**.
> "Two burgers, charged for one. That's our bug. We planted it in this demo app, so the judges can see exactly what goes in and what comes out."
- Stop the recording and drag the video into video2pr. **Leave the note box empty.**

### 0:50–1:40: Devin watches (Speaker A)
- Point at the stepper: *Video → Frames → Bug report*.
> "We sample one frame per second and hand the frames straight to **Devin** as attachments. No other model is involved.
> Devin's first job is to watch the recording and write a structured bug report…"
- The report card appears, labelled **Written by Devin** (≈30 s in our runs).
> "…title, exact steps, expected $25.00, actual $12.50, and where in the code it suspects the bug is. We never typed a word."
- Click **Open Devin session** to show Devin working live: it opens the app in a browser, reproduces the bug, and edits the code.

### 1:40–2:20: The PR (Speaker B)
- In our runs the PR opened about **1 minute** after the session started. If it's slow, switch to the backup PR tab and come back.
- Show the **Before / After** card: $12.50 → $25.00, the root cause, and the one-line diff:
  ```diff
  - return sum + item.price * (id === "burger" ? 1 : quantity);
  + return sum + item.price * quantity;
  ```
- Click **View pull request**: a real GitHub PR with the bug report, root cause, and before/after screenshots.
> "Video in, PR out. A human only has to click Merge."

### 2:20–2:45: Why it matters (Speaker A)
> "Engineers spend hours turning vague reports into reproducible ones. video2pr removes that step completely.
> And because it's Devin, it doesn't just guess at a patch: it reproduces the bug in a real browser and verifies the fix with screenshots before it opens the PR."
- (If the parallel feature is done:) "And it scales: drop in five recordings, get five Devin sessions working in parallel."

### 2:45–3:00: Close (both)
> "Anyone who can hit record can now file a fix. Thanks! Happy to show you any of the PRs."

---

## How it works (for Q&A)
```
upload video ─► ffmpeg (1 fps, ≤12 frames)
            ─► Devin API: upload frames as attachments, create session with a JSON schema
            ─► Devin: structured bug report → reproduce in browser → fix → screenshots → PR
            ─► our backend polls the session: report card, live messages, PR link, before/after
```
- Stack: FastAPI + vanilla JS, Devin API v1 (attachments, sessions, structured output). Also supports OpenAI/Anthropic vision as an optional provider.
- Mock mode replays the whole flow offline for rehearsals and as a stage backup.

## Likely judge questions
- **"Is the bug real?"** It's planted on purpose so the demo is controlled. We have 4 different kinds: math, mobile CSS, search logic, and double-submit.
- **"What if Devin gets it wrong?"** Nothing merges automatically. A human reviews the PR, which includes before/after proof.
- **"Why not just GPT-4o for the report?"** One agent owns the whole loop: the same session that understood the video also reproduces and verifies the fix, so there's no context lost between handoffs.
- **"Real-world use?"** Embed a "record bug" button in any app (support widget, QA, beta testers) and point it at your repo.

### One-line answers (memorize these)
| Question | One line |
|---|---|
| Is the bug real? | Planted on purpose so the demo is reliable, and we planted four different kinds: math, mobile CSS, search logic, double-submit. |
| What if Devin gets it wrong? | It only opens a PR; a human reviews it, with before/after screenshots as proof. |
| Why not just GPT-4o for the report? | The same Devin session that understood the video also reproduces and verifies the fix, so no context is lost in a handoff. |
| Real-world use? | A "record a bug" button in any app (support, QA, beta testers) that points at your repo. |
| How is this different from Sentry / session replay? | Those show you what happened; we go from a plain phone video to a reviewable fix, with no SDK installed in the app. |
| What if the video is unclear? | The bug report card shows exactly what Devin understood before it touches code, and the optional note field adds the missing context. |

## Backup plan
| Problem | Do this |
|---|---|
| Devin slow (>2 min) | Talk through "why it matters", then show the backup PR #4 tab |
| Wi-Fi / API down | Switch to the mock-mode tab and run the same flow |
| Upload fails | Use the pre-recorded `docs/media/bug1_quantity.mp4` |
