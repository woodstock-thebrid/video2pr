(() => {
  if (!location.pathname.startsWith("/demo")) return;

  const MAX_SECONDS = 30;
  const FILENAME = "bug-recording.webm";

  const style = document.createElement("style");
  style.textContent = `
    .rb-widget{position:fixed;top:96px;right:16px;z-index:2147483000;display:flex;flex-direction:column;align-items:flex-end;gap:8px;font:600 13px Arial,sans-serif}
    .rb-button{display:inline-flex;align-items:center;gap:8px;padding:10px 14px;border:0;border-radius:999px;background:#14253d;color:#fff;font:inherit;cursor:pointer;box-shadow:0 6px 18px rgba(20,37,61,.28)}
    .rb-button:hover{background:#22395a}
    .rb-button:disabled{opacity:.75;cursor:progress}
    .rb-button.rb-recording{background:#b42318}
    .rb-dot{width:9px;height:9px;border-radius:50%;background:#e5484d;flex:none}
    .rb-recording .rb-dot{background:#fff;animation:rb-pulse 1s infinite}
    .rb-timer{font-variant-numeric:tabular-nums}
    .rb-message{max-width:260px;padding:8px 12px;border-radius:8px;background:#fff;color:#14253d;font-weight:400;line-height:1.35;box-shadow:0 6px 18px rgba(20,37,61,.2)}
    .rb-message.rb-error{background:#fdecea;color:#8a1c12;border:1px solid #f3b8b1}
    @keyframes rb-pulse{50%{opacity:.3}}
    @media(max-width:420px){.rb-widget{top:82px;right:12px}}
  `;
  document.head.appendChild(style);

  const widget = document.createElement("div");
  widget.className = "rb-widget";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "rb-button";
  const message = document.createElement("div");
  message.className = "rb-message";
  message.setAttribute("role", "status");
  message.setAttribute("aria-live", "polite");
  message.hidden = true;
  widget.append(button, message);
  document.body.appendChild(widget);

  let recorder = null;
  let stream = null;
  let chunks = [];
  let startedAt = 0;
  let tickTimer = null;
  let stopTimer = null;

  function setLabel(text, timer) {
    button.replaceChildren();
    const dot = document.createElement("span");
    dot.className = "rb-dot";
    dot.setAttribute("aria-hidden", "true");
    button.append(dot, document.createTextNode(text));
    if (timer !== undefined) {
      const time = document.createElement("span");
      time.className = "rb-timer";
      time.textContent = timer;
      button.append(time);
    }
  }

  function showMessage(text, isError = false) {
    message.textContent = text;
    message.classList.toggle("rb-error", isError);
    message.hidden = !text;
  }

  function formatElapsed(ms) {
    const total = Math.floor(ms / 1000);
    return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
  }

  function reset() {
    clearInterval(tickTimer);
    clearTimeout(stopTimer);
    stream?.getTracks().forEach(track => track.stop());
    recorder = null;
    stream = null;
    chunks = [];
    button.disabled = false;
    button.classList.remove("rb-recording");
    setLabel("Report a bug");
  }

  function pickMimeType() {
    const candidates = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"];
    return candidates.find(type => window.MediaRecorder?.isTypeSupported?.(type)) || "";
  }

  async function startRecording() {
    showMessage("");
    if (!navigator.mediaDevices?.getDisplayMedia || !window.MediaRecorder) {
      showMessage("Screen recording isn't supported in this browser. Try desktop Chrome, Edge, or Firefox.", true);
      return;
    }
    try {
      stream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false, preferCurrentTab: true });
    } catch (error) {
      stream = null;
      const cancelled = error?.name === "NotAllowedError" || error?.name === "AbortError";
      showMessage(cancelled ? "Screen sharing was cancelled, so nothing was recorded." : `Couldn't start screen recording: ${error?.message || error}`, true);
      return;
    }

    const mimeType = pickMimeType();
    try {
      recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    } catch (error) {
      reset();
      showMessage(`Couldn't start the recorder: ${error?.message || error}`, true);
      return;
    }
    chunks = [];
    recorder.addEventListener("dataavailable", event => {
      if (event.data?.size) chunks.push(event.data);
    });
    recorder.addEventListener("stop", () => sendRecording(new Blob(chunks, { type: "video/webm" })));
    stream.getVideoTracks().forEach(track => track.addEventListener("ended", stopRecording));

    recorder.start(1000);
    startedAt = Date.now();
    button.classList.add("rb-recording");
    setLabel("Stop & send", "00:00");
    tickTimer = setInterval(() => setLabel("Stop & send", formatElapsed(Date.now() - startedAt)), 250);
    stopTimer = setTimeout(stopRecording, MAX_SECONDS * 1000);
    showMessage(`Recording. Show the bug, then press Stop & send (stops automatically after ${MAX_SECONDS} s).`);
  }

  function stopRecording() {
    if (!recorder || recorder.state === "inactive") return;
    clearInterval(tickTimer);
    clearTimeout(stopTimer);
    recorder.stop();
  }

  async function sendRecording(blob) {
    stream?.getTracks().forEach(track => track.stop());
    button.classList.remove("rb-recording");
    button.disabled = true;
    setLabel("Sending…");
    showMessage("Uploading your recording…");

    if (!blob.size) {
      reset();
      showMessage("The recording was empty. Please try again and record for at least a second.", true);
      return;
    }

    const body = new FormData();
    body.append("video", blob, FILENAME);
    try {
      const response = await fetch("/api/reports", { method: "POST", body });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || `Upload failed (HTTP ${response.status}).`);
      if (!payload.job_id) throw new Error("The server didn't return a job id.");

      const jobUrl = `/?job=${encodeURIComponent(payload.job_id)}`;
      const opened = window.open(jobUrl, "_blank");
      if (opened) {
        opened.opener = null;
        reset();
        showMessage("Sent. The investigation opened in a new tab.");
      } else {
        location.assign(jobUrl);
      }
    } catch (error) {
      reset();
      showMessage(`Couldn't send the recording: ${error?.message || error}`, true);
    }
  }

  button.addEventListener("click", () => {
    if (recorder && recorder.state === "recording") stopRecording();
    else if (!recorder) startRecording();
  });

  setLabel("Report a bug");
})();
