const stages = [
  { key: "extracting", label: "Video" },
  { key: "frames", label: "Frames" },
  { key: "analyzing", label: "Bug report" },
  { key: "devin_working", label: "Agent fixing" },
  { key: "pr_opened", label: "PR" }
];
const terminalStages = new Set(["finished", "failed"]);
let selectedFiles = [];
let selectedJobId = null;
let pollTimer = null;
let elapsedTimer = null;
let elapsedTimerJobId = null;
let batchPollTimer = null;
let batchRefreshInFlight = false;
let batchJobIds = [];
let batchJobs = new Map();
let currentView = "job";
let detailFromBoard = false;
let lightboxElement = null;
let lightboxItems = [];
let lightboxIndex = 0;
let lightboxReturnFocus = null;
let lightboxJobId = null;
let renderedJob = null;
let copyFeedbackJobId = null;
let copyFeedbackLabel = "Copied";
let copyFeedbackUntil = 0;
let copyFeedbackTimeout = null;

const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, character => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
}[character]));

function reportMarkdown(job) {
  const report = job.report || {};
  const lines = [
    "## Bug report (written by an AI agent from a screen recording)",
    "",
    `**Page:** ${report.page || ""}`,
    `**Severity:** ${report.severity || ""}`,
    "",
    "**Steps:**",
    ...(report.steps || []).map((step, index) => `${index + 1}. ${step}`),
    "",
    `**Expected:** ${report.expected || ""}`,
    `**Actual:** ${report.actual || ""}`,
    `**Suspected area:** ${report.suspected_area || ""}`
  ];
  if (job.devin_session_url) lines.push("", `Agent session: ${job.devin_session_url}`);
  if (job.pr_url) lines.push("", `Fix PR: ${job.pr_url}`);
  return lines.join("\n");
}

function githubIssueUrl(job) {
  let owner = "woodstock-thebrid";
  let repository = "video2pr";
  if (job.pr_url) {
    try {
      const parsed = new URL(job.pr_url);
      const parts = parsed.pathname.split("/").filter(Boolean);
      if (parsed.hostname === "github.com" && parts.length >= 4 && parts[2] === "pull" && /^\d+$/.test(parts[3])) {
        owner = parts[0];
        repository = parts[1].replace(/\.git$/i, "");
      }
    } catch {}
  }
  const url = new URL(`https://github.com/${encodeURIComponent(owner)}/${encodeURIComponent(repository)}/issues/new`);
  url.searchParams.set("title", job.report?.title || "Bug report");
  url.searchParams.set("body", reportMarkdown(job));
  return url.toString();
}

function setCopyFeedback(jobId, label) {
  copyFeedbackJobId = jobId;
  copyFeedbackLabel = label;
  copyFeedbackUntil = Date.now() + 2000;
  if (copyFeedbackTimeout) clearTimeout(copyFeedbackTimeout);
  const button = document.querySelector("#job-content [data-copy-report]");
  if (button && renderedJob?.job_id === jobId) button.textContent = label;
  copyFeedbackTimeout = setTimeout(() => {
    if (copyFeedbackJobId !== jobId) return;
    copyFeedbackJobId = null;
    copyFeedbackUntil = 0;
    const currentButton = document.querySelector("#job-content [data-copy-report]");
    if (currentButton && renderedJob?.job_id === jobId) currentButton.textContent = "Copy as Markdown";
  }, 2000);
}

function shouldStopPolling(job) {
  return terminalStages.has(job?.stage)
    || (job?.stage === "pr_opened" && job?.comparison_status !== "waiting");
}

function renderCodeDiff(diff) {
  return String(diff ?? "").split("\n").map(line => {
    const escaped = escapeHtml(line);
    if (line.startsWith("+") && !line.startsWith("+++")) return `<span class="diff-add">${escaped}</span>`;
    if (line.startsWith("-") && !line.startsWith("---")) return `<span class="diff-remove">${escaped}</span>`;
    return `<span>${escaped}</span>`;
  }).join("");
}

function formatDuration(milliseconds) {
  const totalSeconds = Math.max(0, Math.round(milliseconds / 1000));
  return `${Math.floor(totalSeconds / 60)}m ${totalSeconds % 60}s`;
}

function timestampMilliseconds(job, stage) {
  const timestamp = Date.parse(job?.timestamps?.[stage] || "");
  return Number.isFinite(timestamp) ? timestamp : null;
}

function jobPrDuration(job) {
  const startedAt = timestampMilliseconds(job, "extracting");
  const pullRequestAt = timestampMilliseconds(job, "pr_opened");
  return startedAt === null || pullRequestAt === null
    ? null
    : formatDuration(pullRequestAt - startedAt);
}

function renderJobTimer(job) {
  const duration = jobPrDuration(job);
  if (duration !== null) {
    return `<div class="video-pr-timer video-pr-timer-complete">Video → PR <strong>in ${duration}</strong></div>`;
  }
  const startedAt = timestampMilliseconds(job, "extracting");
  if (startedAt === null || job.stage === "failed" || job.devin_state === "failed") return "";
  return `<div class="video-pr-timer video-pr-timer-live" id="video-pr-timer" aria-live="off">Elapsed ${formatDuration(Date.now() - startedAt)}</div>`;
}

function clearElapsedTimer() {
  if (elapsedTimer) clearInterval(elapsedTimer);
  elapsedTimer = null;
  elapsedTimerJobId = null;
}

function syncElapsedTimer(job) {
  const timerElement = document.querySelector("#video-pr-timer");
  if (!timerElement) {
    clearElapsedTimer();
    return;
  }
  if (elapsedTimer && elapsedTimerJobId === job.job_id) return;
  clearElapsedTimer();
  const startedAt = timestampMilliseconds(job, "extracting");
  if (startedAt === null) return;
  elapsedTimerJobId = job.job_id;
  elapsedTimer = setInterval(() => {
    if (selectedJobId !== job.job_id || currentView === "batchBoard") {
      clearElapsedTimer();
      return;
    }
    const currentTimer = document.querySelector("#video-pr-timer");
    if (!currentTimer) {
      clearElapsedTimer();
      return;
    }
    currentTimer.textContent = `Elapsed ${formatDuration(Date.now() - startedAt)}`;
  }, 1000);
}

function renderComparison(job) {
  if (job.comparison_status === "waiting") {
    return `<section class="comparison-card comparison-waiting" aria-live="polite">
      <div class="block-title"><span>BEFORE / AFTER</span><span>IN PROGRESS</span></div>
      <div class="comparison-skeleton"><span></span><span></span></div>
      <p>Waiting for the agent's verification screenshots…</p>
    </section>`;
  }
  if (job.comparison_status === "unavailable") {
    const prLink = job.pr_url
      ? `<a class="comparison-pr-link" href="${escapeHtml(job.pr_url)}" target="_blank" rel="noopener noreferrer">View the PR for screenshots ↗</a>`
      : "";
    return `<section class="comparison-card">
      <div class="block-title"><span>BEFORE / AFTER</span><span>UNAVAILABLE</span></div>
      <p>Verification screenshots are unavailable.</p>${prLink}
    </section>`;
  }
  if (job.comparison_status !== "ready" || !job.comparison) return "";

  const comparison = job.comparison;
  const beforeSrc = comparison.before_src || comparison.before_url;
  const afterSrc = comparison.after_src || comparison.after_url;
  const rootCauseMarkup = comparison.root_cause
    ? `<p class="comparison-root-cause"><strong>Root cause</strong> ${escapeHtml(comparison.root_cause)}</p>`
    : "";
  const codeDiffMarkup = comparison.code_diff
    ? `<pre class="comparison-diff">${renderCodeDiff(comparison.code_diff)}</pre>`
    : "";
  return `<section class="comparison-card">
    <div class="block-title"><span>BEFORE / AFTER</span><span>VERIFIED</span></div>
    <div class="comparison-images">
      <div class="comparison-image"><span>BEFORE</span><button class="comparison-lightbox-trigger" type="button" data-lightbox-index="0" data-lightbox-src="${escapeHtml(beforeSrc)}" data-lightbox-label="BEFORE" aria-label="View before screenshot full size"><img src="${escapeHtml(beforeSrc)}" alt="Before screenshot"></button></div>
      <div class="comparison-image"><span>AFTER</span><button class="comparison-lightbox-trigger" type="button" data-lightbox-index="1" data-lightbox-src="${escapeHtml(afterSrc)}" data-lightbox-label="AFTER" aria-label="View after screenshot full size"><img src="${escapeHtml(afterSrc)}" alt="After screenshot"></button></div>
    </div>
    ${rootCauseMarkup}${codeDiffMarkup}
  </section>`;
}

function ensureLightbox() {
  if (lightboxElement) return lightboxElement;
  lightboxElement = document.createElement("div");
  lightboxElement.className = "comparison-lightbox";
  lightboxElement.hidden = true;
  lightboxElement.innerHTML = `
    <div class="comparison-lightbox-backdrop"></div>
    <div class="comparison-lightbox-dialog" role="dialog" aria-modal="true" aria-label="Before and after screenshots">
      <div class="comparison-lightbox-header">
        <span class="comparison-lightbox-label"></span>
        <button class="comparison-lightbox-close" type="button" aria-label="Close image viewer">Close <span aria-hidden="true">×</span></button>
      </div>
      <div class="comparison-lightbox-stage">
        <button class="comparison-lightbox-nav" type="button" data-lightbox-previous aria-label="Show previous screenshot">‹</button>
        <img class="comparison-lightbox-image" alt="">
        <button class="comparison-lightbox-nav" type="button" data-lightbox-next aria-label="Show next screenshot">›</button>
      </div>
    </div>`;
  lightboxElement.addEventListener("click", event => {
    if (event.target === lightboxElement || event.target.classList.contains("comparison-lightbox-backdrop")) {
      closeLightbox();
    }
  });
  lightboxElement.querySelector(".comparison-lightbox-close").addEventListener("click", closeLightbox);
  lightboxElement.querySelector("[data-lightbox-previous]").addEventListener("click", () => showLightboxImage(lightboxIndex - 1));
  lightboxElement.querySelector("[data-lightbox-next]").addEventListener("click", () => showLightboxImage(lightboxIndex + 1));
  document.body.append(lightboxElement);
  return lightboxElement;
}

function showLightboxImage(index) {
  if (!lightboxItems.length) return;
  lightboxIndex = (index + lightboxItems.length) % lightboxItems.length;
  const item = lightboxItems[lightboxIndex];
  const image = lightboxElement.querySelector(".comparison-lightbox-image");
  image.src = item.src;
  image.alt = `${item.label.toLowerCase()} screenshot`;
  lightboxElement.querySelector(".comparison-lightbox-label").textContent = item.label;
}

function openLightbox(trigger) {
  lightboxItems = [...document.querySelectorAll("#job-content .comparison-lightbox-trigger")].map(button => ({
    src: button.dataset.lightboxSrc,
    label: button.dataset.lightboxLabel
  }));
  const index = Number(trigger.dataset.lightboxIndex);
  if (!lightboxItems.length || !lightboxItems[index]) return;
  const lightbox = ensureLightbox();
  lightboxIndex = index;
  lightboxReturnFocus = trigger;
  lightboxJobId = selectedJobId;
  showLightboxImage(index);
  lightbox.hidden = false;
  document.body.classList.add("lightbox-open");
  lightbox.querySelector(".comparison-lightbox-close").focus();
}

function closeLightbox() {
  if (!lightboxElement || lightboxElement.hidden) return;
  lightboxElement.hidden = true;
  document.body.classList.remove("lightbox-open");
  const returnFocus = lightboxReturnFocus;
  lightboxReturnFocus = null;
  lightboxJobId = null;
  if (returnFocus?.isConnected) returnFocus.focus();
}

document.addEventListener("keydown", event => {
  if (!lightboxElement || lightboxElement.hidden) return;
  if (event.key === "Escape") {
    event.preventDefault();
    closeLightbox();
  } else if (event.key === "ArrowLeft") {
    event.preventDefault();
    showLightboxImage(lightboxIndex - 1);
  } else if (event.key === "ArrowRight") {
    event.preventDefault();
    showLightboxImage(lightboxIndex + 1);
  }
});

function setSelectedFiles(fileList) {
  const files = [...fileList];
  if (!files.length) return;
  if (files.some(file => !file.type.startsWith("video/"))) {
    document.querySelector("#upload-title").textContent = "Choose a video file";
    return;
  }
  selectedFiles = files;
  const totalSize = files.reduce((total, file) => total + file.size, 0);
  document.querySelector("#upload-title").textContent = files.length === 1
    ? files[0].name
    : `${files.length} videos selected`;
  document.querySelector("#upload-subtitle").textContent = `${(totalSize / 1024 / 1024).toFixed(1)} MB · ready to analyze`;
  document.querySelector("#drop-zone").classList.add("has-file");
  const button = document.querySelector("#submit-button");
  button.disabled = false;
  button.querySelector("span").textContent = files.length > 1
    ? `Start ${files.length} parallel fixes`
    : "Analyze recording";
}

function renderStepper(stage) {
  const current = stage === "finished" || stage === "pr_opened" ? 4 : stage === "failed" ? -1 : ({
    extracting: 0, analyzing: 2, dispatching: 3, devin_working: 3
  }[stage] ?? 0);
  document.querySelector("#stage-stepper").innerHTML = stages.map((item, index) => {
    const complete = current >= 0 && index < current;
    const active = index === current;
    return `<div class="step ${complete ? "complete" : ""} ${active ? "active" : ""}"><span class="step-circle">${complete ? "✓" : index + 1}</span><span>${item.label}</span></div>`;
  }).join("");
}

function formatStage(stage, job) {
  if (stage === "analyzing" && job?.vision_provider === "devin") {
    return "AI agent is watching the recording";
  }
  return ({
    extracting: "Extracting video frames",
    analyzing: "Writing your bug report",
    dispatching: "Handing the report to the AI agent",
    devin_working: "AI agent is working on a fix",
    pr_opened: "Pull request opened",
    finished: "Session finished",
    failed: "Investigation hit a snag"
  }[stage] || stage);
}

function renderJob(job) {
  if (lightboxJobId && lightboxJobId !== job.job_id) closeLightbox();
  renderedJob = job;
  selectedJobId = job.job_id;
  document.querySelector("#empty-progress").hidden = true;
  document.querySelector("#job-view").hidden = false;
  document.querySelector("#stage-stepper").hidden = false;
  document.querySelector("#job-content").hidden = false;
  document.querySelector("#batch-view").hidden = true;
  document.querySelector("#live-indicator").classList.toggle("is-done", shouldStopPolling(job));
  renderStepper(job.stage);

  const frameMarkup = job.frame_urls?.length
    ? `<div class="result-block"><div class="block-title"><span>FRAMES FROM THE VIDEO</span><span>${job.frame_urls.length} selected</span></div><div class="filmstrip">${job.frame_urls.map((url, index) => `<a href="${escapeHtml(url)}" target="_blank" rel="noreferrer" class="frame"><img src="${escapeHtml(url)}" alt="Extracted video frame ${index + 1}" loading="lazy"><span>${String(index + 1).padStart(2, "0")}</span></a>`).join("")}</div></div>`
    : "";
  let reportMarkup = "";
  if (job.report) {
    const report = job.report;
    const authorBadge = job.vision_provider === "devin"
      ? '<span class="report-author">Written by AI agent</span>'
      : "";
    const copyLabel = copyFeedbackJobId === job.job_id && Date.now() < copyFeedbackUntil
      ? copyFeedbackLabel
      : "Copy as Markdown";
    reportMarkup = `<article class="report-card"><div class="report-top"><span class="report-label">BUG REPORT</span>${authorBadge}<span class="severity severity-${escapeHtml(report.severity)}">${escapeHtml(report.severity)}</span></div><h3>${escapeHtml(report.title)}</h3><p class="report-page">${escapeHtml(report.page)}</p><div class="report-facts"><div><span>EXPECTED</span><p>${escapeHtml(report.expected)}</p></div><div><span>ACTUAL</span><p>${escapeHtml(report.actual)}</p></div></div><div class="report-steps"><strong>REPRODUCTION</strong><ol>${(report.steps || []).map(step => `<li>${escapeHtml(step)}</li>`).join("")}</ol></div><p class="suspected"><strong>Suspected area</strong> ${escapeHtml(report.suspected_area)}</p><div class="report-actions"><button type="button" class="report-action" data-copy-report>${copyLabel}</button><button type="button" class="report-action" data-open-issue>Open as GitHub issue</button></div></article>`;
  }
  const messagesMarkup = job.devin_messages?.length
    ? `<div class="result-block messages-block"><div class="block-title"><span>AGENT ACTIVITY</span><span>${job.devin_messages.length} updates</span></div><div class="message-feed">${job.devin_messages.slice(-8).map(message => `<div class="message"><span class="message-dot"></span><p>${escapeHtml(message.message)}</p></div>`).join("")}</div></div>`
    : "";
  const prMarkup = job.pr_url
    ? `<a class="pr-button" href="${escapeHtml(job.pr_url)}" target="_blank" rel="noreferrer"><span><small>READY FOR REVIEW</small>View pull request</span><span aria-hidden="true">↗</span></a>`
    : "";
  const errorMarkup = job.error ? `<div class="error-card"><strong>We couldn't finish this run.</strong><p>${escapeHtml(job.error)}</p></div>` : "";
  const waitingMarkup = job.devin_state === "waiting_for_user" && job.devin_session_url
    ? `<a class="needs-input" href="${escapeHtml(job.devin_session_url)}" target="_blank" rel="noreferrer">Agent needs input — open session ↗</a>`
    : "";
  const analyzingSessionMarkup = job.vision_provider === "devin" && job.stage === "analyzing" && job.devin_session_url
    ? `<a class="needs-input session-link" href="${escapeHtml(job.devin_session_url)}" target="_blank" rel="noreferrer">Open agent session ↗</a>`
    : "";
  const statusMarkup = waitingMarkup || `<span>${formatStage(job.stage, job)}</span>${analyzingSessionMarkup}`;
  const backMarkup = detailFromBoard
    ? '<button class="back-to-board" id="back-to-board" type="button">← Back to board</button>'
    : "";
  const timerMarkup = renderJobTimer(job);
  document.querySelector("#job-content").innerHTML = `
    ${backMarkup}
    <div class="job-status"><span class="status-orbit ${shouldStopPolling(job) ? "settled" : ""}"></span>${statusMarkup}<small>${escapeHtml(job.stage.replaceAll("_", " "))}</small></div>
    ${timerMarkup}${frameMarkup}${reportMarkup}${renderComparison(job)}${messagesMarkup}${prMarkup}${errorMarkup}`;
  if (timerMarkup.includes('id="video-pr-timer"')) syncElapsedTimer(job);
  else clearElapsedTimer();
  renderRecent();
}

function renderBatchStageDots(job) {
  const current = ({
    extracting: 0,
    analyzing: 2,
    dispatching: 3,
    devin_working: 3,
    pr_opened: 4,
    finished: 4,
    failed: 4
  }[job.stage] ?? 0);
  return `<div class="parallel-stage-dots" aria-label="Stage: ${escapeHtml(formatStage(job.stage, job))}">${stages.map((stage, index) => {
    const complete = job.stage === "finished" || index < current;
    const active = index === current && !terminalStages.has(job.stage);
    const failed = index === current && job.stage === "failed";
    return `<span class="parallel-stage-dot ${complete ? "complete" : ""} ${active ? "active" : ""} ${failed ? "failed" : ""}" title="${escapeHtml(stage.label)}"></span>`;
  }).join("")}</div>`;
}

function renderBatchBoard() {
  const jobs = batchJobIds.map(jobId => batchJobs.get(jobId)).filter(Boolean);
  const runningCount = jobs.filter(job => !shouldStopPolling(job)).length;
  const pullRequestCount = jobs.filter(job => job.pr_url).length;
  const runningSummary = runningCount
    ? `${runningCount} agent session${runningCount === 1 ? "" : "s"} running in parallel`
    : `${jobs.length} agent session${jobs.length === 1 ? "" : "s"} finished`;
  const cards = jobs.map(job => {
    const reportMarkup = job.report
      ? `<div class="parallel-card-report"><strong>${escapeHtml(job.report.title)}</strong>${job.vision_provider === "devin" ? '<span class="report-author">Written by AI agent</span>' : ""}</div>`
      : '<p class="parallel-card-pending">Bug report in progress</p>';
    const prDuration = job.pr_url ? jobPrDuration(job) : null;
    const prTimeMarkup = prDuration !== null
      ? `<span class="parallel-pr-time">PR in ${prDuration}</span>`
      : "";
    const sessionLink = job.devin_session_url
      ? `<a href="${escapeHtml(job.devin_session_url)}" target="_blank" rel="noopener noreferrer">Agent session ↗</a>`
      : "";
    const prLink = job.pr_url
      ? `<a href="${escapeHtml(job.pr_url)}" target="_blank" rel="noopener noreferrer">Pull request ↗</a>`
      : "";
    const thumbnails = job.comparison_status === "ready" && job.comparison
      ? `<div class="parallel-thumbnails">
          <a href="${escapeHtml(job.comparison.before_src || job.comparison.before_url)}" target="_blank" rel="noopener noreferrer"><img src="${escapeHtml(job.comparison.before_src || job.comparison.before_url)}" alt="Before screenshot"></a>
          <a href="${escapeHtml(job.comparison.after_src || job.comparison.after_url)}" target="_blank" rel="noopener noreferrer"><img src="${escapeHtml(job.comparison.after_src || job.comparison.after_url)}" alt="After screenshot"></a>
        </div>`
      : "";
    return `<article class="parallel-job-card" data-batch-job="${escapeHtml(job.job_id)}" tabindex="0" role="button" aria-label="Open ${escapeHtml(job.upload_name || "video")} details">
      <div class="parallel-card-heading"><strong>${escapeHtml(job.upload_name || "Video")}</strong><span>${escapeHtml(formatStage(job.stage, job))}</span></div>
      ${renderBatchStageDots(job)}
      ${prTimeMarkup}
      ${reportMarkup}
      <div class="parallel-card-links">${sessionLink}${prLink}</div>
      ${thumbnails}
    </article>`;
  }).join("");
  document.querySelector("#empty-progress").hidden = true;
  document.querySelector("#job-view").hidden = false;
  document.querySelector("#stage-stepper").hidden = true;
  document.querySelector("#job-content").hidden = true;
  document.querySelector("#batch-view").hidden = false;
  document.querySelector("#live-indicator").classList.toggle("is-done", jobs.length > 0 && jobs.every(shouldStopPolling));
  document.querySelector("#batch-view").innerHTML = `
    <div class="parallel-board-heading">
      <strong>${runningSummary} · ${pullRequestCount} PR${pullRequestCount === 1 ? "" : "s"} opened</strong>
      <span>${jobs.length} videos</span>
    </div>
    <div class="parallel-job-grid">${cards}</div>`;
  renderRecent();
}

function showBatchJob(jobId) {
  const job = batchJobs.get(jobId);
  if (!job) return;
  currentView = "batchDetail";
  detailFromBoard = true;
  renderJob(job);
}

function showBatchBoard() {
  clearElapsedTimer();
  closeLightbox();
  currentView = "batchBoard";
  detailFromBoard = false;
  selectedJobId = null;
  document.querySelector("#stage-stepper").hidden = true;
  document.querySelector("#job-content").hidden = true;
  document.querySelector("#batch-view").hidden = false;
  renderBatchBoard();
}

async function refreshBatch() {
  if (batchRefreshInFlight || !batchJobIds.length) return;
  batchRefreshInFlight = true;
  try {
    const activeJobIds = batchJobIds.filter(jobId => {
      const job = batchJobs.get(jobId);
      return !job || !shouldStopPolling(job);
    });
    const updates = await Promise.all(activeJobIds.map(async jobId => {
      const response = await fetch(`/api/reports/${encodeURIComponent(jobId)}`);
      return response.ok ? response.json() : null;
    }));
    updates.filter(Boolean).forEach(job => batchJobs.set(job.job_id, job));

    if (currentView === "batchBoard") {
      renderBatchBoard();
    } else if (currentView === "batchDetail" && batchJobs.has(selectedJobId)) {
      renderJob(batchJobs.get(selectedJobId));
    }
    await refreshRecent();
    if (batchJobIds.every(jobId => {
      const job = batchJobs.get(jobId);
      return job && shouldStopPolling(job);
    })) {
      clearInterval(batchPollTimer);
      batchPollTimer = null;
    }
  } catch (error) {
    console.error("Unable to refresh batch", error);
  } finally {
    batchRefreshInFlight = false;
  }
}

function renderRecent(jobs) {
  if (jobs) window.recentJobs = jobs;
  const recent = window.recentJobs || [];
  document.querySelector("#job-total").textContent = `${recent.length} ${recent.length === 1 ? "job" : "jobs"}`;
  document.querySelector("#recent-jobs").innerHTML = recent.length ? recent.slice(0, 8).map(job => `
    <button class="recent-job ${job.job_id === selectedJobId ? "selected" : ""}" data-job="${escapeHtml(job.job_id)}">
      <span class="recent-icon">${job.pr_url ? "✓" : "↗"}</span>
      <span class="recent-job-copy"><strong>${escapeHtml(job.report?.title || "Video investigation")}</strong><small>${escapeHtml(job.stage === "pr_opened" && job.comparison_status === "waiting" ? "Waiting for verification screenshots" : formatStage(job.stage, job))}</small></span>
      <span class="recent-chevron">→</span>
    </button>`).join("") : '<p class="recent-empty">Your recent jobs will show up here.</p>';
}

async function refreshSelected() {
  if (!selectedJobId) return;
  try {
    const response = await fetch(`/api/reports/${encodeURIComponent(selectedJobId)}`);
    if (!response.ok) return;
    const job = await response.json();
    window.currentJob = job;
    renderJob(job);
    if (shouldStopPolling(job)) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
    await refreshRecent();
  } catch (error) {
    console.error("Unable to refresh report", error);
  }
}

async function refreshRecent() {
  try {
    const response = await fetch("/api/reports");
    if (response.ok) renderRecent(await response.json());
  } catch (error) {
    console.error("Unable to refresh recent jobs", error);
  }
}

document.querySelector("#video-file").addEventListener("change", event => setSelectedFiles(event.target.files));
const dropZone = document.querySelector("#drop-zone");
dropZone.addEventListener("dragover", event => {
  event.preventDefault();
  dropZone.classList.add("dragging");
});
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragging"));
dropZone.addEventListener("drop", event => {
  event.preventDefault();
  dropZone.classList.remove("dragging");
  setSelectedFiles(event.dataTransfer.files);
});

document.querySelector("#submit-button").addEventListener("click", async () => {
  if (!selectedFiles.length) return;
  clearElapsedTimer();
  closeLightbox();
  const button = document.querySelector("#submit-button");
  button.disabled = true;
  button.querySelector("span").textContent = selectedFiles.length > 1
    ? "Starting parallel fixes…"
    : "Uploading your recording…";
  const body = new FormData();
  const isBatch = selectedFiles.length > 1;
  if (isBatch) {
    selectedFiles.forEach(file => body.append("videos", file));
  } else {
    body.append("video", selectedFiles[0]);
  }
  body.append("note", document.querySelector("#note").value);
  try {
    const endpoint = isBatch ? "/api/reports/batch" : "/api/reports";
    const response = await fetch(endpoint, { method: "POST", body });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Upload failed.");
    await refreshRecent();
    if (isBatch) {
      if (batchPollTimer) clearInterval(batchPollTimer);
      batchPollTimer = null;
      currentView = "batchBoard";
      detailFromBoard = false;
      selectedJobId = null;
      batchJobIds = result.job_ids;
      batchJobs = new Map();
      await refreshBatch();
      if (batchJobIds.some(jobId => {
        const job = batchJobs.get(jobId);
        return !job || !shouldStopPolling(job);
      })) {
        batchPollTimer = setInterval(refreshBatch, 2000);
      }
    } else {
      currentView = "job";
      detailFromBoard = false;
      selectedJobId = result.job_id;
      window.currentJob = { stage: "extracting" };
      await refreshSelected();
      if (pollTimer) clearInterval(pollTimer);
      if (!shouldStopPolling(window.currentJob)) pollTimer = setInterval(refreshSelected, 2000);
    }
  } catch (error) {
    document.querySelector("#job-content").innerHTML = `<div class="error-card">${escapeHtml(error.message)}</div>`;
    document.querySelector("#batch-view").hidden = true;
    document.querySelector("#empty-progress").hidden = true;
    document.querySelector("#job-view").hidden = false;
  } finally {
    button.disabled = false;
    button.querySelector("span").textContent = selectedFiles.length > 1
      ? `Start ${selectedFiles.length} parallel fixes`
      : "Analyze recording";
  }
});

document.querySelector("#batch-view").addEventListener("click", event => {
  if (event.target.closest("a")) return;
  const card = event.target.closest("[data-batch-job]");
  if (card) showBatchJob(card.dataset.batchJob);
});
document.querySelector("#batch-view").addEventListener("keydown", event => {
  if (event.target.closest("a")) return;
  const card = event.target.closest("[data-batch-job]");
  if (card && (event.key === "Enter" || event.key === " ")) {
    event.preventDefault();
    showBatchJob(card.dataset.batchJob);
  }
});
document.querySelector("#job-content").addEventListener("click", async event => {
  const copyButton = event.target.closest("[data-copy-report]");
  if (copyButton && renderedJob?.report) {
    try {
      await navigator.clipboard.writeText(reportMarkdown(renderedJob));
      setCopyFeedback(renderedJob.job_id, "Copied");
    } catch {
      setCopyFeedback(renderedJob.job_id, "Copy unavailable");
    }
    return;
  }
  const issueButton = event.target.closest("[data-open-issue]");
  if (issueButton && renderedJob?.report) {
    window.open(githubIssueUrl(renderedJob), "_blank", "noopener,noreferrer");
    return;
  }
  const lightboxTrigger = event.target.closest(".comparison-lightbox-trigger");
  if (lightboxTrigger) {
    openLightbox(lightboxTrigger);
    return;
  }
  if (event.target.closest("#back-to-board")) showBatchBoard();
});

document.querySelector("#recent-jobs").addEventListener("click", async event => {
  const button = event.target.closest("[data-job]");
  if (!button) return;
  clearElapsedTimer();
  closeLightbox();
  currentView = "job";
  detailFromBoard = false;
  selectedJobId = button.dataset.job;
  if (pollTimer) clearInterval(pollTimer);
  await refreshSelected();
  if (!shouldStopPolling(window.currentJob)) pollTimer = setInterval(refreshSelected, 2000);
});

async function initialize() {
  await refreshRecent();
  const jobId = new URLSearchParams(window.location.search).get("job");
  if (!jobId) return;
  selectedJobId = jobId;
  await refreshSelected();
  if (!shouldStopPolling(window.currentJob)) pollTimer = setInterval(refreshSelected, 2000);
}

initialize();
