// The phone side of the dictation: record a clip, post it, show both
// languages. No framework; the whole page is this file and index.html.
//
// Settings live in localStorage on the phone, not on the server: the
// server has no idea who is talking to it, and the desktop app keeps its
// own file, so each front end remembers its own choices.

"use strict";

const $ = (id) => document.getElementById(id);
const SETTINGS = ["translate_mode", "tidy_mode", "autocopy", "copy_english"];
const TOKEN_KEY = "stt_token";

let recorder = null;
let chunks = [];
let entryNo = 0;

function headers() {
  const token = localStorage.getItem(TOKEN_KEY);
  return token ? { "X-Token": token } : {};
}

function setStatus(text) {
  $("status").textContent = text;
}

// --- settings -------------------------------------------------------------

function loadSettings() {
  for (const key of SETTINGS) {
    const saved = localStorage.getItem("stt_" + key);
    if (saved === null) continue;
    const el = $(key);
    if (el.type === "checkbox") el.checked = saved === "true";
    else el.value = saved;
  }
  syncEnglishCopy();
}

function saveSettings() {
  for (const key of SETTINGS) {
    const el = $(key);
    localStorage.setItem("stt_" + key, el.type === "checkbox" ? el.checked : el.value);
  }
  syncEnglishCopy();
}

// "Always copy English" needs a translation to exist, same rule as the
// desktop app: greyed out while translation is off.
function syncEnglishCopy() {
  $("copy_english").disabled = $("translate_mode").value === "off";
}

// --- server ---------------------------------------------------------------

async function checkStatus() {
  try {
    const res = await fetch("/api/status", { headers: headers() });
    if (res.status === 401) {
      const token = prompt("This server asks for a token:");
      if (token) localStorage.setItem(TOKEN_KEY, token);
      return checkStatus();
    }
    const info = await res.json();
    if (info.error) {
      setStatus("Model failed to load: " + info.error);
      return;
    }
    if (!info.ready) {
      setStatus("Loading the speech model on the computer…");
      setTimeout(checkStatus, 1500);
      return;
    }
    $("device").textContent = "Whisper " + info.model + " · " + info.device + " · v" + info.version;
    setStatus("Ready - press Record and start speaking (EN or ES).");
    $("record").disabled = false;
  } catch (err) {
    setStatus("Cannot reach the computer. Is the server running? " + err.message);
    setTimeout(checkStatus, 3000);
  }
}

// Browsers differ in what they can record; pick the first container the
// phone supports. Whisper decodes any of them on the server.
function pickMimeType() {
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
  return candidates.find((t) => window.MediaRecorder && MediaRecorder.isTypeSupported(t)) || "";
}

async function startRecording() {
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (err) {
    setStatus("Microphone blocked: " + err.message + " (the page must be opened over https)");
    return;
  }
  const mimeType = pickMimeType();
  recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
  chunks = [];
  recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
  recorder.onstop = () => {
    stream.getTracks().forEach((t) => t.stop());
    send(new Blob(chunks, { type: recorder.mimeType }));
  };
  recorder.start();
  $("record").textContent = "Stop";
  $("record").classList.add("recording");
  setStatus("Recording… press Stop when you are done.");
}

function stopRecording() {
  $("record").textContent = "Record";
  $("record").classList.remove("recording");
  $("record").disabled = true;
  setStatus("Transcribing on the computer…");
  recorder.stop();
}

async function send(blob) {
  const form = new FormData();
  form.append("clip", blob, "clip");
  form.append("translate_mode", $("translate_mode").value);
  form.append("tidy_mode", $("tidy_mode").value);
  try {
    const res = await fetch("/api/dictate", { method: "POST", body: form, headers: headers() });
    if (!res.ok) {
      const detail = (await res.json().catch(() => ({}))).detail || res.statusText;
      setStatus("Failed: " + detail);
      return;
    }
    show(await res.json());
  } catch (err) {
    setStatus("Failed: " + err.message);
  } finally {
    $("record").disabled = false;
  }
}

// --- results --------------------------------------------------------------

function show(result) {
  if (!result.text) {
    setStatus(result.note || "No speech detected.");
    return;
  }
  entryNo += 1;
  const other = result.lang === "en" ? "es" : "en";
  const stamp = "#" + entryNo + " · " + new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  $("title-" + result.lang).textContent = result.lang_name + " - spoken";
  $("title-" + other).textContent = (result.lang === "en" ? "Español" : "English") + " - translation";
  $("badge").textContent = "Detected: " + result.lang_name + " (" + Math.round(result.probability * 100) + "%)";
  append(result.lang, stamp, result.text);
  if (result.translation) append(other, stamp, result.translation);

  const wantsEnglish = $("copy_english").checked && !$("copy_english").disabled;
  let copied = "";
  if ($("autocopy").checked) {
    const english = result.lang === "en" ? result.text : result.translation;
    const toCopy = wantsEnglish && english ? english : result.text;
    copied = copyText(toCopy) ? (toCopy === result.text ? " · copied" : " · English copied") : "";
  }
  const notes = result.notes && result.notes.length ? " · " + result.notes.join(" · ") : "";
  const engine = result.engine ? " · translated " + result.engine : "";
  setStatus("Done - " + Math.round(result.duration) + "s of audio" + engine + copied + notes + ".");
}

// Entry headers are in the text box like the desktop app, and the Copy
// buttons strip them so what you paste is just the words.
function append(lang, stamp, text) {
  const box = $("pane-" + lang);
  box.value = (box.value ? box.value.trimEnd() + "\n\n" : "") + stamp + "\n" + text;
  box.scrollTop = box.scrollHeight;
}

function stripStamps(text) {
  return text.split("\n").filter((line) => !/^#\d+ · /.test(line)).join("\n").trim();
}

function copyText(text) {
  if (!text) return false;
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).catch(() => {});
    return true;
  }
  // http://localhost on the PC itself: the clipboard API is still allowed
  // there, but fall back to the old way just in case.
  const area = document.createElement("textarea");
  area.value = text;
  document.body.appendChild(area);
  area.select();
  const ok = document.execCommand("copy");
  area.remove();
  return ok;
}

// --- wiring ---------------------------------------------------------------

$("record").addEventListener("click", () => {
  if (recorder && recorder.state === "recording") stopRecording();
  else startRecording();
});
for (const key of SETTINGS) $(key).addEventListener("change", saveSettings);
for (const btn of document.querySelectorAll("[data-copy]")) {
  btn.addEventListener("click", () => {
    if (copyText(stripStamps($("pane-" + btn.dataset.copy).value))) {
      const label = btn.textContent;
      btn.textContent = "Copied";
      setTimeout(() => { btn.textContent = label; }, 1200);
    }
  });
}
for (const btn of document.querySelectorAll("[data-clear]")) {
  btn.addEventListener("click", () => { $("pane-" + btn.dataset.clear).value = ""; });
}

loadSettings();
checkStatus();
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/static/sw.js").catch(() => {});
