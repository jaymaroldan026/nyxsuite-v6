"use strict";

const BRIDGE = "http://127.0.0.1:8870/";
const SETUP_VIEW = BRIDGE + "#setup";

const logEl = document.getElementById("log");
const pill = document.getElementById("statePill");

function log(msg, kind) {
  const line = document.createElement("div");
  line.className = "logline" + (kind ? " " + kind : "");
  const t = new Date().toLocaleTimeString();
  line.textContent = `[${t}] ${msg}`;
  logEl.appendChild(line);
  logEl.scrollTop = logEl.scrollHeight;
}

function setPill(on) {
  pill.textContent = on ? "bridge online" : "bridge offline";
  pill.className = "pill " + (on ? "on" : "off");
}

function bridgeUp() {
  return fetch(BRIDGE, { method: "HEAD", cache: "no-store" }).then(() => true).catch(() => false);
}
function wait(ms) { return new Promise((r) => setTimeout(r, ms)); }

async function pollUntilUp(timeoutMs) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (await bridgeUp()) return true;
    await wait(1000);
  }
  return false;
}

function startAgent() {
  return new Promise((resolve, reject) => {
    try {
      chrome.runtime.sendNativeMessage("com.nyxsuite.agent", { type: "start_agent" }, (resp) => {
        if (chrome.runtime.lastError) { reject(new Error(chrome.runtime.lastError.message)); return; }
        resolve(resp || {});
      });
    } catch (e) { reject(e); }
  });
}

function goToInstaller() {
  setPill(true);
  log("Bridge is online — opening the install web UI…", "ok");
  setTimeout(() => { window.location.href = SETUP_VIEW; }, 600);
}

// Show only the step block for the user's OS — no scrolling past the other two.
function filterOsBlocks() {
  const plat = ((navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || "").toLowerCase();
  const os = plat.indexOf("win") >= 0 ? "windows"
    : (plat.indexOf("mac") >= 0 ? "macos" : (plat.indexOf("linux") >= 0 ? "linux" : ""));
  if (!os) return;
  document.querySelectorAll("#steps .os").forEach((blk) => {
    const h3 = blk.querySelector("h3");
    const h = (h3 ? h3.textContent : "").toLowerCase();
    blk.style.display = h.indexOf(os) >= 0 ? "" : "none";
  });
}

function showSteps() {
  const s = document.getElementById("steps");
  filterOsBlocks();
  s.hidden = false;
  s.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function tryStart() {
  const btn = document.getElementById("startBtn");
  btn.disabled = true;
  log("Asking the Nyx agent to start the bridge…");
  try {
    const r = await startAgent();
    if (r && r.ok === false) {
      log("The agent couldn't start the bridge: " + (r.error || "unknown error"), "bad");
      log("The app may not be installed yet — do the one-time setup step below.", "muted");
      showSteps();
      btn.disabled = false;
      return;
    }
    log("Bridge starting — waiting for it to come online (up to 40s)…");
    const up = await pollUntilUp(40000);
    if (up) { goToInstaller(); }
    else {
      log("The bridge didn't come online. It probably isn't installed on this PC yet.", "bad");
      showSteps();
      btn.disabled = false;
    }
  } catch (e) {
    log("Couldn't reach the native agent: " + e.message, "bad");
    log("This PC hasn't been set up yet. Do the one-time step below, then click Retry.", "muted");
    showSteps();
    btn.disabled = false;
  }
}

async function retry() {
  log("Checking for the bridge…");
  if (await bridgeUp()) { goToInstaller(); }
  else {
    setPill(false);
    log("Still not running. Make sure you launched it (steps below).", "bad");
    showSteps();
  }
}

document.getElementById("startBtn").addEventListener("click", tryStart);
document.getElementById("retryBtn").addEventListener("click", retry);
document.getElementById("showStepsBtn").addEventListener("click", showSteps);
document.querySelectorAll("[data-copy]").forEach((b) => {
  b.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(b.getAttribute("data-copy"));
      const prev = b.textContent; b.textContent = "Copied";
      setTimeout(() => { b.textContent = prev; }, 1500);
    } catch (e) { /* clipboard blocked — ignore */ }
  });
});

(async () => {
  log("Checking whether the Nyx Suite bridge is already running…");
  if (await bridgeUp()) { goToInstaller(); }
  else {
    setPill(false);
    log("Bridge is not running yet.", "muted");
    log('Click "Start the bridge". On a brand-new PC, use "Show setup steps" for the one-time launcher step.', "muted");
  }
})();
