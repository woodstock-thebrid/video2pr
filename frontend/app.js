const stages = [
  { key: "extracting", label: "Video" },
  { key: "frames", label: "Frames" },
  { key: "analyzing", label: "Bug report" },
  { key: "devin_working", label: "Devin fixing" },
  { key: "pr_opened", label: "PR" }
];
const terminalStages = new Set(["pr_opened", "finished", "failed"]);
let selectedFile = null;
let selectedJobId = null;
let pollTimer = null;

const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, character => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
}[character]));

function setSelectedFile(file) {
  if (!file) return;
  if (!file.type.startsWith("video/")) {
    document.querySelector("#upload-title").textContent = "Choose a video file";
    return;
  }
  selectedFile = file;
  document.querySelector("#upload-title").textContent = file.name;
  document.querySelector("#upload-subtitle").textContent = `${(file.size / 1024 / 1024).toFixed(1)} MB · ready to analyze`;
  document.querySelector("#drop-zone").classList.add("has-file");
  document.querySelector("#submit-button").disabled = false;
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
    return "Devin is watching the recording";
  }
  return ({
    extracting: "Extracting video frames",
    analyzing: "Writing your bug report",
    dispatching: "Handing the report to Devin",
    devin_working: "Devin is working on a fix",
    pr_opened: "Pull request opened",
    finished: "Session finished",
    failed: "Investigation hit a snag"
  }[stage] || stage);
}

function renderJob(job) {
  selectedJobId = job.job_id;
  document.querySelector("#empty-progress").hidden = true;
  document.querySelector("#job-view").hidden = false;
  document.querySelector("#live-indicator").classList.toggle("is-done", terminalStages.has(job.stage));
  renderStepper(job.stage);

  const frameMarkup = job.frame_urls?.length
    ? `<div class="result-block"><div class="block-title"><span>FRAMES FROM THE VIDEO</span><span>${job.frame_urls.length} selected</span></div><div class="filmstrip">${job.frame_urls.map((url, index) => `<a href="${escapeHtml(url)}" target="_blank" rel="noreferrer" class="frame"><img src="${escapeHtml(url)}" alt="Extracted video frame ${index + 1}" loading="lazy"><span>${String(index + 1).padStart(2, "0")}</span></a>`).join("")}</div></div>`
    : "";
  let reportMarkup = "";
  if (job.report) {
    const report = job.report;
    const authorBadge = job.vision_provider === "devin"
      ? '<span class="report-author">Written by Devin</span>'
      : "";
    reportMarkup = `<article class="report-card"><div class="report-top"><span class="report-label">BUG REPORT</span>${authorBadge}<span class="severity severity-${escapeHtml(report.severity)}">${escapeHtml(report.severity)}</span></div><h3>${escapeHtml(report.title)}</h3><p class="report-page">${escapeHtml(report.page)}</p><div class="report-facts"><div><span>EXPECTED</span><p>${escapeHtml(report.expected)}</p></div><div><span>ACTUAL</span><p>${escapeHtml(report.actual)}</p></div></div><div class="report-steps"><strong>REPRODUCTION</strong><ol>${(report.steps || []).map(step => `<li>${escapeHtml(step)}</li>`).join("")}</ol></div><p class="suspected"><strong>Suspected area</strong> ${escapeHtml(report.suspected_area)}</p></article>`;
  }
  const messagesMarkup = job.devin_messages?.length
    ? `<div class="result-block messages-block"><div class="block-title"><span>DEVIN ACTIVITY</span><span>${job.devin_messages.length} updates</span></div><div class="message-feed">${job.devin_messages.slice(-8).map(message => `<div class="message"><span class="message-dot"></span><p>${escapeHtml(message.message)}</p></div>`).join("")}</div></div>`
    : "";
  const prMarkup = job.pr_url
    ? `<a class="pr-button" href="${escapeHtml(job.pr_url)}" target="_blank" rel="noreferrer"><span><small>READY FOR REVIEW</small>View pull request</span><span aria-hidden="true">↗</span></a>`
    : "";
  const errorMarkup = job.error ? `<div class="error-card"><strong>We couldn't finish this run.</strong><p>${escapeHtml(job.error)}</p></div>` : "";
  const waitingMarkup = job.devin_state === "waiting_for_user" && job.devin_session_url
    ? `<a class="needs-input" href="${escapeHtml(job.devin_session_url)}" target="_blank" rel="noreferrer">Devin needs input — open session ↗</a>`
    : "";
  const analyzingSessionMarkup = job.vision_provider === "devin" && job.stage === "analyzing" && job.devin_session_url
    ? `<a class="needs-input session-link" href="${escapeHtml(job.devin_session_url)}" target="_blank" rel="noreferrer">Open Devin session ↗</a>`
    : "";
  const statusMarkup = waitingMarkup || `<span>${formatStage(job.stage, job)}</span>${analyzingSessionMarkup}`;
  document.querySelector("#job-content").innerHTML = `
    <div class="job-status"><span class="status-orbit ${terminalStages.has(job.stage) ? "settled" : ""}"></span>${statusMarkup}<small>${escapeHtml(job.stage.replaceAll("_", " "))}</small></div>
    ${frameMarkup}${reportMarkup}${messagesMarkup}${prMarkup}${errorMarkup}`;
  renderRecent();
}

function renderRecent(jobs) {
  if (jobs) window.recentJobs = jobs;
  const recent = window.recentJobs || [];
  document.querySelector("#job-total").textContent = `${recent.length} ${recent.length === 1 ? "job" : "jobs"}`;
  document.querySelector("#recent-jobs").innerHTML = recent.length ? recent.slice(0, 8).map(job => `
    <button class="recent-job ${job.job_id === selectedJobId ? "selected" : ""}" data-job="${escapeHtml(job.job_id)}">
      <span class="recent-icon">${job.pr_url ? "✓" : "↗"}</span>
      <span class="recent-job-copy"><strong>${escapeHtml(job.report?.title || "Video investigation")}</strong><small>${escapeHtml(formatStage(job.stage, job))}</small></span>
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
    if (terminalStages.has(job.stage)) {
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

document.querySelector("#video-file").addEventListener("change", event => setSelectedFile(event.target.files[0]));
const dropZone = document.querySelector("#drop-zone");
dropZone.addEventListener("dragover", event => {
  event.preventDefault();
  dropZone.classList.add("dragging");
});
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragging"));
dropZone.addEventListener("drop", event => {
  event.preventDefault();
  dropZone.classList.remove("dragging");
  setSelectedFile(event.dataTransfer.files[0]);
});

document.querySelector("#submit-button").addEventListener("click", async () => {
  if (!selectedFile) return;
  const button = document.querySelector("#submit-button");
  button.disabled = true;
  button.innerHTML = "<span>Uploading your recording…</span><span>↗</span>";
  const body = new FormData();
  body.append("video", selectedFile);
  body.append("note", document.querySelector("#note").value);
  try {
    const response = await fetch("/api/reports", { method: "POST", body });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Upload failed.");
    selectedJobId = result.job_id;
    window.currentJob = { stage: "extracting" };
    await refreshRecent();
    await refreshSelected();
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(refreshSelected, 2000);
  } catch (error) {
    button.disabled = false;
    button.innerHTML = "<span>Try again</span><span aria-hidden=\"true\">→</span>";
    document.querySelector("#job-content").innerHTML = `<div class="error-card">${escapeHtml(error.message)}</div>`;
    document.querySelector("#empty-progress").hidden = true;
    document.querySelector("#job-view").hidden = false;
  }
});

document.querySelector("#recent-jobs").addEventListener("click", async event => {
  const button = event.target.closest("[data-job]");
  if (!button) return;
  selectedJobId = button.dataset.job;
  if (pollTimer) clearInterval(pollTimer);
  await refreshSelected();
  if (!terminalStages.has(window.currentJob?.stage)) pollTimer = setInterval(refreshSelected, 2000);
});

async function initialize() {
  await refreshRecent();
  const jobId = new URLSearchParams(window.location.search).get("job");
  if (!jobId) return;
  selectedJobId = jobId;
  await refreshSelected();
  if (!terminalStages.has(window.currentJob?.stage)) pollTimer = setInterval(refreshSelected, 2000);
}

initialize();
