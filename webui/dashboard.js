"use strict";

const HOST = location.hostname || "127.0.0.1";
const TOKEN = (typeof window !== "undefined" && window.__NYX_TOKEN__) || "";
function tokenHeaders() { return TOKEN ? { "X-Nyx-Token": TOKEN, "X-Nyxify-Token": TOKEN } : {}; }
function adspowerStateText(r) {
  if (!r || !r.adspower_open_profile_id) return "";
  if (r.adspower_open === true) return "Open";
  if (r.adspower_open === false) return "Closed";
  return "Checking";
}

const PRODUCTS = {
  nyx: {
    base: `http://${HOST}:8865`, key: "profile_id",
    tiles: ["pending", "running", "done", "failed"],
    sortFields: ["model", "created_at", "status"],
    columns: [
      { h: "AdsPower ID", f: r => r.profile_id || "", s: "" },
      { h: "AdsPower", f: adspowerStateText, s: "" },
      { h: "Username", f: r => (r.username || "").replace(/^\s*snapchat\s*:\s*/i, ""), s: "" },
      { h: "Model", f: r => r.model || "", s: "model" },
      { h: "Date Added", f: r => (r.created_at || "").slice(0, 19).replace("T", " "), s: "created_at" },
      { h: "Status", badge: true, f: r => r.status || "", s: "status" },
      { h: "Last Step", f: r => r.last_step || "", s: "" },
    ],
    runner: [],
    queue: [["Rerun Failed", "/queue/rerun_failed", ""], ["Reset Stuck", "/queue/reset_stuck", ""],
            ["Flush", "/bot/finish_remaining", ""], ["Clear Completed", "/queue/prune_completed", ""],
            ["Remove Missing", "/queue/remove_missing_profile", ""], ["Clear Queue", "/queue/clear", "bad"]],
    row: [["Mark Done", "/queue/mark_done", ""], ["Relaunch", "/queue/relaunch", ""], ["Remove", "/queue/remove", "bad"]],
    group: [["Mark Done", "/queue/mark_done", ""], ["Relaunch", "/queue/relaunch", ""], ["Remove", "/queue/remove", "bad"]],
  },
  nyxify: {
    base: `http://${HOST}:8866`, key: "row_key",
    tiles: ["pending", "ready", "running", "done", "failed"],
    sortFields: ["model", "created_at", "status"],
    columns: [
      { h: "AdsPower ID", f: r => r.adspower_id || r.adspower_profile_id || "", s: "" },
      { h: "AdsPower", f: adspowerStateText, s: "" },
      { h: "Username", f: r => (r.username || "").replace(/^\s*snapchat\s*:\s*/i, ""), s: "" },
      { h: "Model", f: r => r.model || "", s: "model" },
      { h: "Date Added", f: r => (r.created_at || "").slice(0, 19).replace("T", " "), s: "created_at" },
      { h: "Proxy", f: r => r.proxy_address || "", s: "" },
      { h: "Status", badge: true, f: r => r.status || "", s: "status" },
      { h: "Last Step", f: r => r.last_step || "", s: "" },
      { h: "Error", f: r => r.error || "", s: "" },
    ],
    runner: [],
    queue: [["Reset Failed", "/queue/reset_failed", ""], ["Clear Queue", "/queue/clear", "bad"]],
    row: [["Remove", "/queue/remove", "bad"]],
    group: [["Remove", "/queue/remove", "bad"]],
  },
};

const state = {
  nyx: { rows: new Map(), counts: {}, bot: {}, usage: null, health: null, live: null, config: {}, search: "", sort: "", dir: 1, statusFilter: "", checked: new Set(), advancedVisible: false },
  nyxify: { rows: new Map(), counts: {}, bot: {}, usage: null, health: null, live: null, config: {}, search: "", sort: "", dir: 1, statusFilter: "", checked: new Set(), fullautoVisible: false, advancedVisible: false },
  version: "",
  update: { checked: false, available: false, current: "", latest: "", latest_name: "", notes: "", backups: [] },
};
let active = "nyx";
const selected = { nyx: null, nyxify: null };

const el = id => document.getElementById(id);
const keyOf = (p, row) => String(row[PRODUCTS[p].key] || row.profile_id || row.row_key || "");

function applyProductSnapshot(p, snap) {
  if (!snap || snap.error) return;
  const m = new Map();
  (snap.rows || []).forEach(r => { const k = keyOf(p, r); if (k) m.set(k, r); });
  state[p].rows = m;
  state[p].counts = snap.counts || {};
  state[p].bot = snap.bot || {};
  state[p].usage = snap.adspower_usage || null;
  state[p].health = snap.adspower_health || null;
  state[p].live = snap.adspower_live || null;
  if (snap.config) state[p].config = snap.config;
}

function applyUpdate(ev) {
  const p = ev.product; if (!state[p]) return;
  const m = state[p].rows;
  (ev.rows || []).forEach(r => { const k = keyOf(p, r); if (k) m.set(k, r); });
  (ev.removed || []).forEach(k => m.delete(k));
  if (ev.counts) state[p].counts = ev.counts;
  if (ev.bot) state[p].bot = ev.bot;
  if (ev.adspower_usage !== undefined && ev.adspower_usage !== null) state[p].usage = ev.adspower_usage;
  if (ev.adspower_health !== undefined) state[p].health = ev.adspower_health;
  if (ev.adspower_live !== undefined) state[p].live = ev.adspower_live;
}

function onMessage(data) {
  let ev; try { ev = JSON.parse(data); } catch (e) { return; }
  if (ev.type === "snapshot") {
    const st = ev.status || {};
    state.version = (st.bridge || {}).version || "";
    const prods = st.products || {};
    Object.keys(PRODUCTS).forEach(p => { if (prods[p]) applyProductSnapshot(p, prods[p]); });
  } else if (ev.type === "update") {
    applyUpdate(ev);
  }
  render();
}

let es = null, pollTimer = null;
function connect() {
  try {
    es = new EventSource(`${location.origin}/bridge/events?token=${encodeURIComponent(TOKEN)}`);
    es.onopen = () => { setConn(true); stopPolling(); };
    es.onmessage = e => onMessage(e.data);
    es.onerror = () => { setConn(false); startPolling(); };
  } catch (e) { setConn(false); startPolling(); }
}
function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    try {
      const r = await fetch(`${location.origin}/bridge/status`);
      onMessage(JSON.stringify({ type: "snapshot", status: await r.json() }));
      setConn(true);
    } catch (e) { setConn(false); }
  }, 1500);
}
function stopPolling() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } }
function setConn(ok) { const c = el("conn"); c.textContent = ok ? "live" : "offline"; c.className = "pill " + (ok ? "pill-ok" : "pill-bad"); }

async function callAction(p, path, payload) {
  try {
    const r = await fetch(PRODUCTS[p].base + path, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...tokenHeaders() },
      body: JSON.stringify({ ...(payload || {}), token: TOKEN }),
    });
    const d = await r.json().catch(() => ({}));
    toast(d.message || (d.ok !== false ? "Done." : (d.error || ("HTTP " + r.status))), d.ok !== false);
    return d;
  } catch (e) { toast("Request failed: " + e, false); return { ok: false, error: String(e) }; }
}

// Pull the live config straight from the product API so the Advanced form always
// reflects what is actually persisted. The SSE stream only carries `config` in
// the initial snapshot, so without this the form could render a stale config and
// a Save would write those stale values back — silently wiping real settings.
async function refreshConfig(p) {
  try {
    const r = await fetch(PRODUCTS[p].base + "/config", { headers: tokenHeaders() });
    const d = await r.json().catch(() => ({}));
    if (d && d.config) state[p].config = d.config;
  } catch (e) { /* keep whatever we have */ }
}

async function callBridge(action, payload) {
  try {
    const r = await fetch("/bridge/" + action, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...tokenHeaders() },
      body: JSON.stringify({ ...(payload || {}), token: TOKEN }),
    });
    return await r.json();
  } catch (e) { return { ok: false, error: String(e) }; }
}

function render() {
  el("version").textContent = state.version ? ("v" + state.version) : "v…";
  if (active === "nyx" || active === "nyxify") renderPanel(active);
  // Settings is rendered once on tab open (see setActive); re-rendering on every
  // SSE tick would clobber in-progress edits in the config form.
}

function sortRows(rows, field, dir) {
  if (!field) return rows;
  return [...rows].sort((a, b) => {
    let va = String(a[field] || "").toLowerCase();
    let vb = String(b[field] || "").toLowerCase();
    if (field === "created_at") { va = a[field] || ""; vb = b[field] || ""; }
    if (va < vb) return -1 * dir;
    if (va > vb) return 1 * dir;
    return 0;
  });
}

// Signature of the last rendered output per panel. The dashboard re-runs
// renderPanel on every SSE message and on every 1.5s poll tick; rebuilding the
// whole table via innerHTML each time is the main source of lag (and it wiped
// text selections). When nothing that affects the table has changed we skip the
// rebuild entirely, so steady-state ticks become free.
const panelRenderSig = {};

function panelSignature(p, cfg, s) {
  const rawRows = [...s.rows.values()];
  return [
    (s.bot && s.bot.state) || "",
    (s.bot && s.bot.detail) || "",
    p === "nyxify" ? JSON.stringify(s.usage || {}) : "",
    p === "nyxify" ? JSON.stringify(s.live || {}) : "",
    JSON.stringify(s.counts || {}),
    s.statusFilter || "",
    (s.search || "").toLowerCase().trim(),
    s.sort || "",
    String(s.dir),
    selected[p] || "",
    [...s.checked].sort().join(","),
    rawRows.map(r => keyOf(p, r) + ":" + cfg.columns.map(c => String(c.f(r))).join("|")).join("\n"),
  ].join("##");
}

function renderPanel(p) {
  const cfg = PRODUCTS[p], s = state[p];

  const sig = panelSignature(p, cfg, s);
  const tbodyEl = el("tbody-" + p);
  if (panelRenderSig[p] === sig && tbodyEl && tbodyEl.children.length) {
    return;
  }
  panelRenderSig[p] = sig;

  const bs = (s.bot && s.bot.state) || "…";
  const stEl = el("state-" + p); stEl.textContent = bs; stEl.className = "state " + bs;
  el("detail-" + p).textContent = (s.bot && s.bot.detail) || "";
  if (p === "nyxify") {
    const live = s.live || {};
    el("usage-nyxify").textContent = live.ready ? ("Open AdsPower profiles: " + (live.open || 0)) : "";
  }

  // Tiles — click to filter by status
  const tiles = el("tiles-" + p); tiles.innerHTML = "";
  cfg.tiles.forEach(k => {
    const d = document.createElement("div"); d.className = "tile";
    if (s.statusFilter === k) d.classList.add("tile-active");
    d.dataset.status = k;
    d.innerHTML = `<div class="n">${(s.counts && s.counts[k]) || 0}</div><div class="l">${k}</div>`;
    d.onclick = () => {
      if (s.statusFilter === k) s.statusFilter = "";
      else s.statusFilter = k;
      s.checked.clear();
      renderPanel(p);
    };
    tiles.appendChild(d);
  });
  renderRunnerButtons(p);
  buildToolbar("queue-" + p, cfg.queue, p, false);
  buildToolbar("row-" + p, cfg.row, p, true);
  if (p === "nyxify") renderFullAutoSection();

  const searchEl = el("search-" + p);
  if (searchEl) { searchEl.value = s.search || ""; }
  let rows = [...s.rows.values()];
  const q = (s.search || "").toLowerCase().trim();
  if (q) {
    rows = rows.filter(r => {
      const id = String(r.profile_id || r.adspower_id || r.row_key || "").toLowerCase();
      const uname = String(r.username || r.snapchat_username || "").toLowerCase();
      return id.includes(q) || uname.includes(q);
    });
  }
  // Status filter
  if (s.statusFilter) {
    const sf = s.statusFilter.toUpperCase();
    rows = rows.filter(r => (r.status || "").toUpperCase() === sf);
  }

  // Sort
  rows = sortRows(rows, s.sort, s.dir);

  // Render header with checkbox + sortable columns
  const colCount = cfg.columns.length + 1;
  const allChecked = rows.length > 0 && rows.every(r => s.checked.has(keyOf(p, r)));
  const arrow = f => s.sort === f ? (s.dir === 1 ? " &#9650;" : " &#9660;") : "";
  const ths = `<th class="th-cb"><input type="checkbox" id="cb-all-${p}" ${allChecked ? "checked" : ""}></th>`
    + cfg.columns.map(c => {
        if (c.s) return `<th class="th-sortable" data-sort="${c.s}">${c.h}${arrow(c.s)}</th>`;
        return `<th>${c.h}</th>`;
      }).join("");
  el("thead-" + p).innerHTML = "<tr>" + ths + "</tr>";
  const cbAll = el("cb-all-" + p);
  if (cbAll) {
    cbAll.onclick = e => {
      if (e.target.checked) rows.forEach(r => s.checked.add(keyOf(p, r)));
      else s.checked.clear();
      renderPanel(p);
    };
  }

  const tbody = el("tbody-" + p); tbody.innerHTML = "";
  if (!rows.length) {
    tbody.innerHTML = `<tr><td class="empty" colspan="${colCount}">No rows.</td></tr>`;
    buildGroupToolbar(p);
    return;
  }
  rows.forEach(r => {
    const k = keyOf(p, r);
    const tr = document.createElement("tr"); tr.dataset.key = k;
    if (selected[p] === k) tr.classList.add("sel");
    if (s.checked.has(k)) tr.classList.add("checked");
    tr.innerHTML = `<td class="td-cb"><input type="checkbox" class="cb-row" ${s.checked.has(k) ? "checked" : ""}></td>`
      + cfg.columns.map(c => {
          const v = c.f(r);
          return c.badge ? `<td><span class="badge ${escapeAttr(v)}">${escapeHtml(v)}</span></td>`
                         : `<td title="${escapeAttr(v)}">${escapeHtml(v)}</td>`;
        }).join("");
    const cb = tr.querySelector(".cb-row");
    cb.onclick = e => {
      e.stopPropagation();
      if (e.target.checked) s.checked.add(k); else s.checked.delete(k);
      renderPanel(p);
    };
    tr.onclick = e => {
      if (e.target.closest(".td-cb, .cb-row")) return;
      // Let the user highlight/copy cell text without the row re-render wiping it.
      if (window.getSelection && String(window.getSelection()).length > 0) return;
      selected[p] = (selected[p] === k ? null : k);
      renderPanel(p);
    };
    tbody.appendChild(tr);
  });
  buildGroupToolbar(p);
}

function appendRow(tbody, p, r, cfg) {
  const k = keyOf(p, r);
  const tr = document.createElement("tr"); tr.dataset.key = k;
  if (selected[p] === k) tr.classList.add("sel");
  tr.innerHTML = cfg.columns.map(c => {
    const v = c.f(r);
    return c.badge ? `<td><span class="badge ${escapeAttr(v)}">${escapeHtml(v)}</span></td>`
                   : `<td title="${escapeAttr(v)}">${escapeHtml(v)}</td>`;
  }).join("");
  tr.onclick = () => { selected[p] = (selected[p] === k ? null : k); renderPanel(p); };
  tbody.appendChild(tr);
}

function renderRunnerButtons(p) {
  const bar = el("runner-" + p);
  if (!bar) return;
  const botState = ((state[p].bot || {}).state || "").toLowerCase();
  const isActive = ["running", "paused", "waiting", "blocked"].includes(botState);
  const isPaused = botState === "paused";
  bar.innerHTML = "";
  const g = document.createElement("div"); g.className = "btn-group"; bar.appendChild(g);
  const ss = document.createElement("button");
  ss.className = "btn" + (isActive ? " bad" : " primary");
  ss.textContent = isActive ? "Stop" : "Start";
  ss.onclick = () => callAction(p, isActive ? "/bot/stop" : "/bot/start", {});
  g.appendChild(ss);
  const pr = document.createElement("button");
  pr.className = "btn" + (isPaused ? "" : " warn");
  pr.textContent = isPaused ? "Resume" : "Pause";
  pr.onclick = () => callAction(p, isPaused ? "/bot/resume" : "/bot/pause", {});
  pr.disabled = !isActive;
  g.appendChild(pr);
  bar.style.display = "flex";
}

function buildToolbar(id, defs, p, isRow) {
  const bar = el(id); bar.innerHTML = "";
  if (!defs || !defs.length) { bar.style.display = "none"; return; }
  bar.style.display = "flex";
  let group = null;
  defs.forEach(d => {
    if (d === null) { group = null; return; }
    const [label, path, cls] = d;
    if (!group) { group = document.createElement("div"); group.className = "btn-group"; bar.appendChild(group); }
    const b = document.createElement("button");
    b.className = "btn" + (cls ? (" " + cls) : "");
    b.textContent = label;
    if (isRow) {
      b.disabled = !selected[p];
      b.onclick = () => { const k = selected[p]; if (!k) return; const payload = {}; payload[PRODUCTS[p].key] = k; callAction(p, path, payload); };
    } else {
      b.onclick = () => callAction(p, path, {});
    }
    group.appendChild(b);
  });
}

function buildGroupToolbar(p) {
  const bar = el("group-" + p);
  if (!bar) return;
  const cfg = PRODUCTS[p];
  const defs = cfg.group || [];
  const checked = state[p].checked;
  if (!defs.length || !checked.size) { bar.classList.remove("visible"); return; }
  bar.classList.add("visible");
  bar.innerHTML = `<span class="badge-cb">${checked.size} selected</span>`;
  let group = null;
  defs.forEach(d => {
    if (d === null) { group = null; return; }
    const [label, path, cls] = d;
    if (!group) { group = document.createElement("div"); group.className = "btn-group"; bar.appendChild(group); }
    const b = document.createElement("button");
    b.className = "btn" + (cls ? (" " + cls) : "");
    b.textContent = label;
    b.onclick = () => {
      const keys = [...checked];
      const keyField = cfg.key;
      keys.forEach(k => {
        const payload = { [keyField]: k };
        callAction(p, path, payload);
      });
    };
    group.appendChild(b);
  });
}

const escapeHtml = s => String(s).replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
const escapeAttr = s => String(s).replace(/"/g, "&quot;");

let toastTimer = null;
function toast(msg, ok) {
  const t = el("toast"); t.textContent = msg; t.className = "toast " + (ok ? "ok" : "bad");
  void t.offsetWidth;
  t.classList.add("show");
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.classList.remove("show"); }, 4000);
}

function setActive(p) {
  active = p;
  document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === p));
  document.querySelectorAll(".panel").forEach(s => s.classList.toggle("hidden", s.dataset.product !== p && s.id !== ("panel-" + p)));
  if (p === "settings") renderSettings();
  if (p === "bitmoji") loadBitmoji();
  if (p === "nyx" || p === "nyxify") {
    render();
  }
}

// ---------- Settings panel ----------
async function renderSettings() {
  const autostart = await callBridge("autostart");
  const asEl = el("autostart-toggle");
  if (autostart.ok) asEl.checked = autostart.enabled;

  await refreshConfig("nyx");
  renderAdsPowerModeControls();
  renderUpdatesCard();
  // Refresh backup availability so Roll Back only shows when there's a restore point.
  const backups = await callBridge("list_backups");
  state.update.backups = backups.ok ? (backups.backups || []) : [];
  renderUpdatesCard();
}

function currentAdsPowerControlMode() {
  const mode = String((state.nyx.config || {}).adspower_control_mode || "auto").trim().toLowerCase();
  return ["auto", "api", "gui"].includes(mode) ? mode : "auto";
}

function renderAdsPowerModeControls() {
  const current = currentAdsPowerControlMode();
  document.querySelectorAll("[data-adspower-mode]").forEach(btn => {
    const active = btn.dataset.adspowerMode === current;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-pressed", active ? "true" : "false");
  });
  const feedback = el("adspower-mode-feedback");
  if (feedback && !feedback.dataset.busy) {
    const labels = { auto: "Auto: use API first, then GUI when AdsPower blocks the API.", api: "API: Local API only; GUI fallback disabled.", gui: "GUI: use AdsPower desktop automation first on this device." };
    feedback.textContent = labels[current] || labels.auto;
  }
}

async function saveAdsPowerControlMode(mode) {
  const normalized = String(mode || "").trim().toLowerCase();
  if (!["auto", "api", "gui"].includes(normalized)) return;
  const feedback = el("adspower-mode-feedback");
  if (feedback) {
    feedback.dataset.busy = "1";
    feedback.textContent = "Saving AdsPower control mode...";
  }
  const result = await callAction("nyx", "/config", { adspower_control_mode: normalized });
  if (result && result.config) state.nyx.config = result.config;
  renderAdsPowerModeControls();
  if (feedback) {
    feedback.dataset.busy = "";
    feedback.textContent = result && result.ok !== false
      ? "AdsPower control mode saved: " + normalized.toUpperCase() + ". Restart running bots to apply immediately."
      : (result && (result.error || result.message)) || "Could not save AdsPower control mode.";
  }
}

// Reflect state.update into the Updates card: Apply only shows when an update
// is available; Roll Back only shows when a restore point exists.
function renderUpdatesCard() {
  const u = state.update;
  el("update-current").textContent = u.current || state.nyx.config.version || state.version || "—";
  const latestRow = el("update-latest-row");
  const latestEl = el("update-latest");
  const applyBtn = el("update-apply-btn");
  const rollbackBtn = el("update-rollback-btn");
  const notesEl = el("update-release-notes");
  const backupsEl = el("update-backups");
  if (u.available) {
    latestRow.style.display = "flex";
    latestEl.textContent = u.latest_name || u.latest;
    applyBtn.style.display = "";
    if (u.notes) {
      notesEl.style.display = "block";
      notesEl.innerHTML = "<details><summary>Release Notes</summary><pre>" + escapeHtml(u.notes) + "</pre></details>";
    } else {
      notesEl.style.display = "none";
    }
  } else {
    latestRow.style.display = "none";
    applyBtn.style.display = "none";
    notesEl.style.display = "none";
  }
  const hasBackups = !!(u.backups && u.backups.length);
  rollbackBtn.style.display = hasBackups ? "" : "none";
  if (backupsEl) backupsEl.textContent = hasBackups ? ("Restore point available: v" + u.backups[0]) : "";
}

// ---------- Update check + indicator ----------
async function runUpdateCheck(showFeedback) {
  const r = await callBridge("check_update");
  const u = state.update;
  u.checked = true;
  if (!r.ok) {
    u.available = false;
    if (r.current) u.current = r.current;
    if (showFeedback) el("update-feedback").textContent = r.message || "Check failed.";
  } else {
    u.current = r.current || u.current;
    u.available = !!r.update_available;
    u.latest = r.latest || "";
    u.latest_name = r.latest_name || "";
    u.notes = r.release_notes || "";
    if (showFeedback) {
      el("update-feedback").textContent = r.update_available
        ? (r.message || `Update ${r.latest} available.`)
        : (r.message || `Up to date (${r.current || "—"}).`);
    }
  }
  refreshUpdateIndicator();
  if (active === "settings") renderUpdatesCard();
  return r;
}

function refreshUpdateIndicator() {
  const ind = el("update-indicator");
  if (!ind) return;
  if (state.update.available) {
    ind.style.display = "";
    ind.textContent = "update " + (state.update.latest || "ready");
  } else {
    ind.style.display = "none";
  }
}

// ---------- Advanced Config (Nyx section, upper-right) ----------
function renderNyxAdvanced() {
  const body = el("nyx-advanced-body");
  if (!body) return;
  const v = state.nyx.config || {};
  const opt = (val, label) => `<option value="${val}" ${v.outfit_style === val ? "selected" : ""}>${label}</option>`;
  const mode = currentAdsPowerControlMode();
  const modeOpt = (val, label) => `<option value="${val}" ${mode === val ? "selected" : ""}>${label}</option>`;
  body.innerHTML = `
    <div class="adv-grid">
      <label class="adv-field"><span>Pending threshold</span><input id="cfg-pending_threshold" class="input" value="${escapeAttr(v.pending_threshold || 1)}"></label>
      <label class="adv-field"><span>Max parallel</span><input id="cfg-max_parallel_profiles" class="input" value="${escapeAttr(v.max_parallel_profiles || 5)}"></label>
      <label class="adv-field"><span>Automation speed (%)</span><input id="cfg-automation_speed" class="input" type="number" min="5" max="100" value="${escapeAttr(Math.round((Number(v.automation_speed) || 1) * 50))}"></label>
      <label class="adv-field"><span>Outfit style</span><select id="cfg-outfit_style" class="input">
        ${opt("default", "Default")}${opt("mixed", "Mixed")}${opt("casual", "Casual")}${opt("sexy", "Sexy")}${opt("no_dresses", "No Dresses")}
      </select></label>
      <div class="adv-field toggle-row"><span class="toggle-text">Hair randomizer</span><label class="toggle-switch"><input id="cfg-hair_randomizer_enabled" type="checkbox" ${v.hair_randomizer_enabled ? "checked" : ""}><span class="toggle-slider"></span></label></div>

    </div>
    <div class="adv-section-label">AdsPower Local API</div>
    <p class="adv-note">NyxSuite connects to AdsPower automatically — just keep the AdsPower app open and logged in. No API key needed. The fields below are optional, only for a custom host/port or an AdsPower that requires a key.</p>
    <div class="adv-grid">
      <label class="adv-field"><span>Control mode</span><select id="cfg-adspower_control_mode" class="input">
        ${modeOpt("auto", "Auto")}${modeOpt("api", "API only")}${modeOpt("gui", "GUI first")}
      </select></label>
      <label class="adv-field"><span>API key (optional)</span><input id="cfg-adspower_api_key" class="input" type="password" autocomplete="off" placeholder="${v.adspower_api_key_set ? "•••••• (saved — leave blank to keep)" : "optional — only if AdsPower requires one"}"></label>
      <label class="adv-field"><span>Host (optional)</span><input id="cfg-adspower_host" class="input" value="${escapeAttr(v.adspower_host || "")}" placeholder="127.0.0.1"></label>
      <label class="adv-field"><span>Port (optional)</span><input id="cfg-adspower_port" class="input" value="${escapeAttr(v.adspower_port || "")}" placeholder="50325"></label>
    </div>
    <div class="adv-actions">
      <button id="cfg-adspower-test-btn" class="btn" type="button">Test AdsPower connection</button>
      <span id="cfg-adspower-test-result" class="muted"></span>
    </div>
    <button id="cfg-save-btn" class="btn primary" type="button">Save Config</button>
  `;
}

// ---------- Advanced Config (Nyxify section) ----------
function renderNyxifyAdvanced() {
  const body = el("nyxify-advanced-body");
  if (!body) return;
  const v = state.nyxify.config || {};
  const banned = Array.isArray(v.blocked_proxies) ? v.blocked_proxies
    : (Array.isArray(v.banned_proxies) ? v.banned_proxies : []);
  body.innerHTML = `
    <div class="adv-grid">
      <label class="adv-field"><span>Max parallel</span><input id="ncfg-max_parallel_profiles" class="input" value="${escapeAttr(v.max_parallel_profiles || 1)}"></label>
      <label class="adv-field"><span>Temporary name</span><input id="ncfg-temporary_profile_name" class="input" value="${escapeAttr(v.temporary_profile_name || "")}"></label>
      <label class="adv-field"><span>AdsPower group</span><input id="ncfg-adspower_group" class="input" value="${escapeAttr(v.adspower_group || "")}"></label>
      <label class="adv-field"><span>Extension category</span><input id="ncfg-extension_category" class="input" value="${escapeAttr(v.extension_category || "")}"></label>
      <label class="adv-field"><span>Tag 1</span><input id="ncfg-tag_one" class="input" value="${escapeAttr(v.tag_one || "")}"></label>
      <label class="adv-field"><span>Tag 2</span><input id="ncfg-tag_two" class="input" value="${escapeAttr(v.tag_two || "")}"></label>
      <div class="adv-field toggle-row"><span class="toggle-text">Apply AdsPower tags <span class="muted">(off = no tags on created profiles)</span></span><label class="toggle-switch"><input id="ncfg-adspower_tags_enabled" type="checkbox" ${v.adspower_tags_enabled === true ? "checked" : ""}><span class="toggle-slider"></span></label></div>
      <div class="adv-field toggle-row"><span class="toggle-text">Push AdsPower ID to SnapBoard</span><label class="toggle-switch"><input id="ncfg-push_adspower_id_enabled" type="checkbox" ${v.push_adspower_id_enabled !== false ? "checked" : ""}><span class="toggle-slider"></span></label></div>
      <div class="adv-field toggle-row"><span class="toggle-text">Proxy Blocker</span><label class="toggle-switch"><input id="ncfg-proxy_blocker_enabled" type="checkbox" ${v.proxy_blocker_enabled !== false ? "checked" : ""}><span class="toggle-slider"></span></label></div>
      <div class="adv-field toggle-row"><span class="toggle-text">Proxy Checker <span class="muted">(uses AdsPower check)</span></span><label class="toggle-switch"><input id="ncfg-proxy_checker_enabled" type="checkbox" ${v.proxy_checker_enabled !== false ? "checked" : ""}><span class="toggle-slider"></span></label></div>
      <div class="adv-field toggle-row"><span class="toggle-text">Full Auto Mode</span><label class="toggle-switch"><input id="ncfg-full_auto_mode_enabled" type="checkbox" ${v.full_auto_mode_enabled === true ? "checked" : ""}><span class="toggle-slider"></span></label></div>
      <div class="adv-field toggle-row"><span class="toggle-text">Continuous Mode <span class="muted">(send completed signups to Nyx)</span></span><label class="toggle-switch"><input id="ncfg-continuous_mode_enabled" type="checkbox" ${v.continuous_mode_enabled === true ? "checked" : ""}><span class="toggle-slider"></span></label></div>
      <div class="adv-field toggle-row"><span class="toggle-text">Disable extensions on create <span class="muted">(off = leave extensions on during signup)</span></span><label class="toggle-switch"><input id="ncfg-disable_extensions_enabled" type="checkbox" ${v.disable_extensions_enabled === true ? "checked" : ""}><span class="toggle-slider"></span></label></div>
    </div>
    <label class="adv-field adv-field-wide"><span>Banned proxies (one per line)</span><textarea id="ncfg-banned_proxies" class="input textarea-full">${escapeHtml(banned.join("\n"))}</textarea></label>
    <button id="ncfg-save-btn" class="btn primary" type="button">Save Config</button>
  `;
}

el("autostart-toggle").addEventListener("change", async () => {
  const enabled = el("autostart-toggle").checked;
  const r = await callBridge("set_autostart", { enabled });
  el("autostart-feedback").textContent = r.ok ? (r.message || "Done.") : (r.error || "Failed.");
});

el("update-check-btn").addEventListener("click", async () => {
  el("update-feedback").textContent = "Checking…";
  await runUpdateCheck(true);
});

el("update-indicator").addEventListener("click", () => setActive("settings"));

el("update-apply-btn").addEventListener("click", async () => {
  const target = state.update.latest_name || state.update.latest || "the latest version";
  const preUpdateVersion = state.version;
  if (!confirm("Apply update to " + target + "?\n\nThe app will download, install, and restart. The browser extension is updated too — you'll need to reload it at chrome://extensions afterward.")) return;
  const fb = el("update-feedback");
  fb.innerHTML = "Updating… the dashboard will refresh automatically.";
  const r = await callBridge("apply_update");
  if (!r.ok) { fb.textContent = r.message || "Update failed."; return; }
  // Poll for bridge restart
  let elapsed = 0;
  const pollInterval = 1500;
  const maxWait = 60000;
  const pollTimer = setInterval(async () => {
    elapsed += pollInterval;
    try {
      const statusR = await fetch("/bridge/status");
      const status = await statusR.json();
      const newVersion = (status.bridge || {}).version || "";
      if (newVersion && newVersion !== preUpdateVersion) {
        clearInterval(pollTimer);
        fb.innerHTML = "Update applied! Refreshing…";
        // Show extension reload banner
        showExtensionReloadBanner(newVersion);
        setTimeout(() => location.reload(), 800);
        return;
      }
      if (newVersion && newVersion === preUpdateVersion) {
        // Bridge back but same version — also refresh
        clearInterval(pollTimer);
        fb.innerHTML = "Bridge restarted. Refreshing…";
        showExtensionReloadBanner(newVersion);
        setTimeout(() => location.reload(), 800);
        return;
      }
    } catch (e) {
      // Bridge still down — keep waiting
    }
    if (elapsed >= maxWait) {
      clearInterval(pollTimer);
      fb.innerHTML = "The bridge is taking longer than expected to restart."
        + ' <button id="manual-reload-btn" class="btn" type="button">Reload now</button>';
      el("manual-reload-btn").addEventListener("click", () => location.reload());
      showExtensionReloadBanner(preUpdateVersion);
    }
  }, pollInterval);
});

function showExtensionReloadBanner(version) {
  const existing = el("ext-reload-banner");
  if (existing) return;
  const banner = document.createElement("div");
  banner.id = "ext-reload-banner";
  banner.className = "ext-reload-banner";
  banner.innerHTML = `Extension updated to v${escapeHtml(version)} — `
    + `<button id="ext-reload-copy" class="btn btn-ghost" type="button">Copy chrome://extensions</button>`
    + ` and paste it into your address bar, then click the reload ↻ on the Nyx / Nyxify extension.`;
  document.querySelector(".topbar")?.after(banner);
  el("ext-reload-copy")?.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText("chrome://extensions");
      toast("Copied chrome://extensions — paste it in the address bar.", true);
    } catch (e) {
      toast("Could not copy. Manually type chrome://extensions in the address bar.", false);
    }
  });
}

el("update-rollback-btn").addEventListener("click", async () => {
  const backups = await callBridge("list_backups");
  const list = backups.ok ? (backups.backups || []) : [];
  state.update.backups = list;
  renderUpdatesCard();
  if (!list.length) { el("update-feedback").textContent = "No restore point available to roll back to."; return; }
  const version = list[0];
  if (!confirm("Are you sure you want to roll back to v" + version + "?\n\nThis restores the previous version's files and restarts the app.")) return;
  el("update-feedback").textContent = "Rolling back…";
  const r = await callBridge("rollback", { version });
  el("update-feedback").textContent = r.message || (r.ok ? "Rolling back..." : "Rollback failed.");
});

el("nyx-advanced-toggle").addEventListener("click", () => {
  const panel = el("nyx-advanced");
  const willShow = panel.hidden;
  state.nyx.advancedVisible = willShow;
  if (willShow) renderNyxAdvanced();
  panel.hidden = !willShow;
  el("nyx-advanced-toggle").classList.toggle("active", willShow);
});

el("nyxify-advanced-toggle").addEventListener("click", async () => {
  const panel = el("nyxify-advanced");
  const willShow = panel.hidden;
  state.nyxify.advancedVisible = willShow;
  if (willShow) {
    await refreshConfig("nyxify");   // always edit the live config, never a stale one
    renderNyxifyAdvanced();
  }
  panel.hidden = !willShow;
  el("nyxify-advanced-toggle").classList.toggle("active", willShow);
});

document.addEventListener("click", async (e) => {
  if (e.target.id === "cfg-save-btn") {
    const speedPct = Math.max(5, Math.min(100, parseInt(el("cfg-automation_speed").value) || 50));
    const cfg = {
      pending_threshold: parseInt(el("cfg-pending_threshold").value) || 1,
      max_parallel_profiles: parseInt(el("cfg-max_parallel_profiles").value) || 5,
      automation_speed: Math.max(0.1, Math.min(2.0, Math.round((speedPct / 50) * 100) / 100)),
      outfit_style: el("cfg-outfit_style").value,
      hair_randomizer_enabled: el("cfg-hair_randomizer_enabled").checked,

      adspower_control_mode: el("cfg-adspower_control_mode") ? el("cfg-adspower_control_mode").value : "auto",
      adspower_host: el("cfg-adspower_host") ? el("cfg-adspower_host").value.trim() : "",
      adspower_port: el("cfg-adspower_port") ? el("cfg-adspower_port").value.trim() : "",
    };
    // Only send the API key when the user typed a new one — a blank masked field
    // means "keep the saved key", so we omit it entirely.
    const apiKeyInput = el("cfg-adspower_api_key");
    const typedKey = apiKeyInput ? apiKeyInput.value.trim() : "";
    if (typedKey) cfg.adspower_api_key = typedKey;
    const r = await callAction("nyx", "/config", cfg);
    if (r && r.config) state.nyx.config = r.config;
    renderAdsPowerModeControls();
    el("config-feedback").textContent = "Config saved.";
  }
  if (e.target && e.target.dataset && e.target.dataset.adspowerMode) {
    await saveAdsPowerControlMode(e.target.dataset.adspowerMode);
  }
  if (e.target.id === "cfg-adspower-test-btn") {
    const out = el("cfg-adspower-test-result");
    if (out) { out.textContent = "Testing…"; out.className = "muted"; }
    // Save first so the test uses any host/port/key just entered.
    if (e.target.dataset.busy === "1") return;
    e.target.dataset.busy = "1";
    try {
      const saveCfg = {
        adspower_host: el("cfg-adspower_host") ? el("cfg-adspower_host").value.trim() : "",
        adspower_port: el("cfg-adspower_port") ? el("cfg-adspower_port").value.trim() : "",
      };
      const apiKeyInput = el("cfg-adspower_api_key");
      const typedKey = apiKeyInput ? apiKeyInput.value.trim() : "";
      if (typedKey) saveCfg.adspower_api_key = typedKey;
      await callAction("nyx", "/config", saveCfg);
      const res = await callBridge("adspower_test");
      if (out) {
        out.textContent = res && res.ok ? "✓ AdsPower Local API is reachable." : (res && res.message) || "AdsPower test failed.";
        out.className = res && res.ok ? "ok-text" : "bad-text";
      }
    } catch (err) {
      if (out) { out.textContent = "Test failed: " + (err && err.message || err); out.className = "bad-text"; }
    } finally {
      e.target.dataset.busy = "";
    }
  }
  if (e.target.id === "ncfg-save-btn") {
    const cfg = {
      max_parallel_profiles: parseInt(el("ncfg-max_parallel_profiles").value) || 1,
      temporary_profile_name: el("ncfg-temporary_profile_name").value,
      adspower_group: el("ncfg-adspower_group").value,
      extension_category: el("ncfg-extension_category").value,
      tag_one: el("ncfg-tag_one").value,
      tag_two: el("ncfg-tag_two").value,
      adspower_tags_enabled: el("ncfg-adspower_tags_enabled").checked,
      push_adspower_id_enabled: el("ncfg-push_adspower_id_enabled").checked,
      proxy_blocker_enabled: el("ncfg-proxy_blocker_enabled").checked,
      proxy_checker_enabled: el("ncfg-proxy_checker_enabled").checked,
      full_auto_mode_enabled: el("ncfg-full_auto_mode_enabled").checked,
      continuous_mode_enabled: el("ncfg-continuous_mode_enabled").checked,
      disable_extensions_enabled: el("ncfg-disable_extensions_enabled").checked,
      banned_proxies: el("ncfg-banned_proxies").value.split(/\r?\n/).map(s => s.trim()).filter(Boolean),
    };
    const res = await callAction("nyxify", "/config", cfg);
    // Keep local state in sync with what was persisted, so re-opening the panel
    // (or a later save) edits the saved config — not a stale snapshot.
    if (res && res.config) { state.nyxify.config = res.config; renderNyxifyAdvanced(); }
    el("nyxify-config-feedback").textContent = "Config saved.";
  }
});

// ---------- Full Auto editor ----------
let currentModels = [];
let selectedModel = "";

function renderFullAutoSection() {
  const section = el("fullauto-section");
  const btn = el("fullauto-toggle-btn");
  if (!section || !btn) return;
  const visible = state.nyxify.fullautoVisible;
  section.style.display = visible ? "block" : "none";
  btn.textContent = visible ? "Hide Full Auto Editor" : "Show Full Auto Editor";
}

async function renderFullAuto() {
  const r = await fetch(`http://${HOST}:8866/models`, { headers: tokenHeaders() }).then(r => r.json()).catch(() => ({ models: [] }));
  currentModels = r.models || [];
  const sel = el("fullauto-model-select");
  sel.innerHTML = currentModels.map(m => `<option value="${escapeAttr(m)}"${m === selectedModel ? " selected" : ""}>${escapeHtml(m)}</option>`).join("");
  if (!selectedModel && currentModels.length) selectedModel = currentModels[0];
  loadFullAutoModel(selectedModel);
}

async function loadFullAutoModel(model) {
  if (!model) { el("fullauto-usernames").value = ""; el("fullauto-signup-names").value = ""; return; }
  const u = await fetch(`http://${HOST}:8866/usernames?model=${encodeURIComponent(model)}`, { headers: tokenHeaders() }).then(r => r.json()).catch(() => ({}));
  el("fullauto-usernames").value = (u.usernames || []).join("\n");
  const s = await fetch(`http://${HOST}:8866/signup_names?model=${encodeURIComponent(model)}`, { headers: tokenHeaders() }).then(r => r.json()).catch(() => ({}));
  el("fullauto-signup-names").value = (s.signup_names || []).join("\n");
}

el("fullauto-model-select").addEventListener("change", () => {
  selectedModel = el("fullauto-model-select").value;
  loadFullAutoModel(selectedModel);
});

el("fullauto-save-usernames").addEventListener("click", async () => {
  const model = el("fullauto-model-select").value;
  if (!model) return;
  const usernames = el("fullauto-usernames").value.split("\n").map(s => s.trim()).filter(Boolean);
  const r = await fetch(`http://${HOST}:8866/usernames`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...tokenHeaders() },
    body: JSON.stringify({ model, usernames, token: TOKEN }),
  }).then(r => r.json());
  toast(r.ok ? "Usernames saved." : (r.error || "Failed."), r.ok);
});

el("fullauto-save-signup").addEventListener("click", async () => {
  const model = el("fullauto-model-select").value;
  if (!model) return;
  const signup_names = el("fullauto-signup-names").value.split("\n").map(s => s.trim()).filter(Boolean);
  const r = await fetch(`http://${HOST}:8866/signup_names`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...tokenHeaders() },
    body: JSON.stringify({ model, signup_names, token: TOKEN }),
  }).then(r => r.json());
  toast(r.ok ? "Signup names saved." : (r.error || "Failed."), r.ok);
});

el("tabs").addEventListener("click", e => { const b = e.target.closest(".tab"); if (b) setActive(b.dataset.tab); });

// Sort on column header click
document.addEventListener("click", e => {
  const th = e.target.closest(".th-sortable");
  if (!th) return;
  const p = th.closest("[data-product]");
  if (!p) return;
  const prod = p.dataset.product;
  const s = state[prod];
  const field = th.dataset.sort;
  if (s.sort === field) s.dir *= -1;
  else { s.sort = field; s.dir = 1; }
  renderPanel(prod);
});

// ---------- Search ----------
["nyx", "nyxify"].forEach(p => {
  const inp = el("search-" + p);
  if (inp) {
    inp.addEventListener("input", () => {
      state[p].search = inp.value;
      render();
    });
  }
});

// ---------- Install Dependencies ----------
let installPollTimer = null;
el("install-deps-btn").addEventListener("click", async () => {
  const btn = el("install-deps-btn");
  const stateEl = el("install-deps-state");
  const outputEl = el("install-deps-output");
  btn.disabled = true;
  stateEl.textContent = "starting...";
  outputEl.style.display = "none";
  el("install-deps-feedback").textContent = "";
  const r = await fetch("/bridge/install_deps", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...tokenHeaders() },
    body: JSON.stringify({ token: TOKEN }),
  });
  const d = await r.json().catch(() => ({}));
  if (!d.ok) { stateEl.textContent = d.message || "Failed"; btn.disabled = false; return; }
  stateEl.textContent = "running...";
  // Poll for completion
  installPollTimer = setInterval(async () => {
    try {
      const r2 = await fetch("/bridge/install_deps_status", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...tokenHeaders() },
        body: JSON.stringify({ token: TOKEN }),
      });
      const d2 = await r2.json().catch(() => ({}));
      if (d2.state === "running") { stateEl.textContent = "running..."; return; }
      if (installPollTimer) { clearInterval(installPollTimer); installPollTimer = null; }
      btn.disabled = false;
      outputEl.textContent = d2.output || "(no output)";
      outputEl.style.display = "block";
      if (d2.state === "done") {
        stateEl.textContent = "done";
        el("install-deps-feedback").textContent = "Dependencies installed successfully.";
      } else {
        stateEl.textContent = "failed";
        el("install-deps-feedback").textContent = "Some steps failed. Check output above.";
      }
    } catch (e) {
      if (installPollTimer) { clearInterval(installPollTimer); installPollTimer = null; }
      btn.disabled = false;
      stateEl.textContent = "error";
      el("install-deps-feedback").textContent = "Status check failed: " + e;
    }
  }, 1000);
});

el("fullauto-toggle-btn").addEventListener("click", () => {
  const willShow = !state.nyxify.fullautoVisible;
  state.nyxify.fullautoVisible = willShow;
  // Toggle the section directly (mirrors the Advanced Config toggle) instead of
  // going through renderPanel — the panelSignature() short-circuit added for the
  // lag fix doesn't track fullautoVisible, so renderPanel would early-return and
  // the editor would never expand.
  renderFullAutoSection();
  if (willShow) renderFullAuto();
});

  // ---------- Configure Nyxmoji (editor) ----------
const bm = {
  catalog: {}, order: [], groups: {}, models: {}, modelNames: [], presets: {}, renderParams: {},
  baseAvatar: "", current: "", active: "", previewPick: {}, featGroup: {}, openGroups: new Set(), loaded: false,
};
const NYX_BASE = PRODUCTS.nyx.base;
const BM_HINTS = {
  preset: m => `Using ${m}'s built-in option for this feature.`,
  fixed: () => "Always use the one option you pick below.",
  random: () => "Tick every option to allow — the bot picks one at random for each profile. Pick a handful that look good together.",
};

async function loadBitmoji() {
  el("bm-status").textContent = "Loading…";
  try {
    const [cat, mod] = await Promise.all([
      fetch(NYX_BASE + "/bitmoji/catalog", { headers: tokenHeaders() }).then(r => r.json()),
      fetch(NYX_BASE + "/bitmoji/models", { headers: tokenHeaders() }).then(r => r.json()),
    ]);
    bm.catalog = (cat && cat.catalog) || {};
    bm.order = ((cat && cat.feature_order) || Object.keys(bm.catalog)).filter(f => bm.catalog[f] && bm.catalog[f].options && bm.catalog[f].options.length);
    bm.groups = (cat && cat.groups) || {};
    bm.baseAvatar = (cat && cat.base_avatar) || "";
    bm.renderParams = (cat && cat.render_params) || {};
    bm.models = (mod && mod.models) || {};
    bm.modelNames = (mod && mod.model_names) || [];
    bm.presets = (mod && mod.model_presets) || {};
    bm.loaded = true;
    if (!bm.current || !bm.modelNames.includes(bm.current)) bm.current = bm.modelNames[0] || "";
    if (!bm.active || !bm.order.includes(bm.active)) bm.active = bm.order[0] || "";
    el("bm-status").textContent = "";
    renderBitmojiModels();
    renderBitmojiAll();
  } catch (e) {
    el("bm-status").textContent = "Could not load Nyxmoji config (is the runner up?).";
  }
}

function renderBitmojiModels() {
  el("bm-model").innerHTML = bm.modelNames.map(m =>
    `<option value="${escapeAttr(m)}"${m === bm.current ? " selected" : ""}>${escapeHtml(m)}</option>`).join("");
}

function modelCfg() {
  if (!bm.models[bm.current]) bm.models[bm.current] = {};
  return bm.models[bm.current];
}

function renderBitmojiAll() {
  if (!bm.loaded) return;
  el("bm-model-tag").textContent = bm.current;
  renderCatBar();
  renderSide();
  renderAvatar();
}


function renderCatBar() {
  const cfg = modelCfg();
  const grouped = (bm.groups && Object.keys(bm.groups).length) ? bm.groups : {};
  // Build feature→group lookup and store on bm for click handler
  const featGroup = {};
  Object.keys(grouped).forEach(g => { (grouped[g] || []).forEach(f => { featGroup[f] = g; }); });
  bm.featGroup = featGroup;
  // Auto-open the active feature's group
  const activeGroup = featGroup[bm.active];
  if (activeGroup) bm.openGroups.add(activeGroup);
  let currentGroup = "";
  let html = "";
  bm.order.forEach(f => {
    const feat = bm.catalog[f];
    if (!feat) return;
    const g = featGroup[f] || "";
    if (g && g !== currentGroup) {
      if (currentGroup) html += `</div>`;  // close previous group's feature container
      currentGroup = g;
      const open = bm.openGroups.has(g);
      html += `<button type="button" class="bm-cat-group bm-cat-group-btn${open ? " open" : ""}" data-group="${escapeAttr(g)}">`
        + `<span class="bm-group-arrow">${open ? "▾" : "▸"}</span>${escapeHtml(g)}</button>`
        + `<div class="bm-cat-features" style="${open ? "" : "display:none"}">`;
    }
    const configured = !!cfg[f];
    html += `<button type="button" class="bm-cat${f === bm.active ? " active" : ""}${configured ? " has-config" : ""}" data-feature="${escapeAttr(f)}">
      <span class="bm-cat-dot"></span><span class="bm-cat-name">${escapeHtml(feat.label || f)}</span></button>`;
  });
  if (currentGroup) html += `</div>`;  // close last group
  el("bm-catbar").innerHTML = html;
}

function renderSide() {
  const f = bm.active; const feat = bm.catalog[f];
  if (!feat) { el("bm-options").innerHTML = ""; return; }
  const sel = modelCfg()[f] || { mode: "preset" };
  const mode = sel.mode || "preset";
  el("bm-feature-title").textContent = feat.label || f;
  el("bm-feature-count").textContent = feat.options.length + " options";
  el("bm-mode-hint").textContent = (BM_HINTS[mode] || (() => ""))(bm.current);
  document.querySelectorAll("#bm-mode-group .bm-mode-btn").forEach(b =>
    b.classList.toggle("active", b.dataset.mode === mode));
  const host = el("bm-options");
  if (mode === "preset") {
    host.className = "bm-options empty";
    // Try to show the model's actual preset value
    const presetParams = bm.presets[bm.current] || {};
    const rp = bm.renderParams[f];
    if (rp && presetParams[rp.param]) {
      host.innerHTML = `<div class="bm-preset-info">Current preset: <code>${escapeHtml(rp.param)}=${escapeHtml(presetParams[rp.param])}</code></div>`;
    } else {
      host.textContent = "Preset — this feature keeps the model's original look.";
    }
    return;
  }
  host.className = "bm-options";
  host.innerHTML = renderOptions(f, feat, sel);
  // Show current selection as thumbnails (not ids) below the option grid.
  const optById = {}; feat.options.forEach(o => { optById[String(o.id)] = o; });
  const thumb = id => {
    const o = optById[String(id)];
    if (feat.type === "color") {
      return `<span class="bm-pool-chip bm-pool-color" title="${escapeAttr(id)}" style="background:${escapeAttr(id)}"></span>`;
    }
    if (o && o.preview) {
      return `<span class="bm-pool-thumb" title="${escapeAttr(id)}"><img loading="lazy" src="${escapeAttr(o.preview)}" alt=""></span>`;
    }
    return `<span class="bm-pool-chip" title="${escapeAttr(id)}">${escapeHtml(id)}</span>`;
  };
  let info = `<div class="bm-selection-info">`;
  if (mode === "fixed") {
    info += sel.id
      ? `<div class="bm-pool-head">Selected</div><div class="bm-pool-grid">${thumb(sel.id)}</div>`
      : `<div class="bm-pool-empty">Click an option above to fix it.</div>`;
    if (sel.color) info += `<div class="bm-pool-head">Color</div><div class="bm-pool-grid"><span class="bm-pool-chip bm-pool-color" title="${escapeAttr(sel.color)}" style="background:${escapeAttr(sel.color)}"></span></div>`;
  } else if (mode === "random") {
    const pool = sel.pool || [];
    info += `<div class="bm-pool-head">Random pool — <strong>${pool.length}</strong> selected</div>`;
    info += pool.length
      ? `<div class="bm-pool-grid">${pool.map(thumb).join("")}</div>`
      : `<div class="bm-pool-empty">Tick options above to add them to the pool.</div>`;
    if (sel.colors && sel.colors.length) {
      info += `<div class="bm-pool-head">Colors — <strong>${sel.colors.length}</strong></div>`;
      info += `<div class="bm-pool-grid">${sel.colors.map(c => `<span class="bm-pool-chip bm-pool-color" title="${escapeAttr(c)}" style="background:${escapeAttr(c)}"></span>`).join("")}</div>`;
    }
  }
  info += `</div>`;
  host.insertAdjacentHTML("beforeend", info);
}

function renderOptions(feature, feat, sel) {
  const chosen = sel.mode === "fixed" ? [sel.id] : (sel.pool || []);
  const chosenSet = new Set(chosen.map(String));
  const chosenColor = sel.color || (sel.colors && sel.colors.length ? sel.colors[0] : "");
  let html = feat.options.map(o => {
    const on = chosenSet.has(String(o.id)) ? " sel" : "";
    if (feat.type === "color") {
      return `<button type="button" class="bm-opt bm-opt-color${on}" data-id="${escapeAttr(o.id)}" title="${escapeAttr(o.id)}" style="background:${escapeAttr(o.id)}"></button>`;
    }
    return `<button type="button" class="bm-opt${on}" data-id="${escapeAttr(o.id)}" title="${escapeAttr(o.id)}"><img loading="lazy" src="${escapeAttr(o.preview || "")}" alt=""></button>`;
  }).join("");
  // Color swatch strip for outfit features
  if (feat.type === "outfit" && feat.options.length) {
    const colors = feat.options.reduce((acc, o) => { (o.colors || []).forEach(c => { if (!acc.includes(c)) acc.push(c); }); return acc; }, []);
    if (colors.length) {
      html += `<div class="bm-color-strip"><span class="bm-color-label">Color:</span>`;
      html += colors.map(c => {
        const on = String(c) === String(chosenColor) ? " sel" : "";
        return `<button type="button" class="bm-opt bm-opt-color${on} bm-opt-swatch" data-color="${escapeAttr(c)}" title="${escapeAttr(c)}" style="background:${escapeAttr(c)}"></button>`;
      }).join("");
      html += `</div>`;
    }
  }
  return html;
}

function shufflePreviewPicks() {
  const cfg = bm.models[bm.current] || {};
  bm.order.forEach(f => {
    const rp = bm.renderParams[f];
    const feat = bm.catalog[f];
    if (!rp || !feat || !feat.options || !feat.options.length) return;
    const sel = cfg[f];
    // Only shuffle features the operator set to Random — pick from THAT pool.
    // Fixed and preset features keep the model's chosen/baseline look so the
    // preview stays a valid render (randomizing everything produced invalid
    // param combinations that 404'd and blanked the preview).
    if (!sel || sel.mode !== "random") { delete bm.previewPick[f]; delete bm.previewPick[f + ":color"]; return; }
    const pool = (sel.pool || []).map(String).filter(id => feat.options.some(o => String(o.id) === id));
    if (!pool.length) { delete bm.previewPick[f]; return; }
    bm.previewPick[f] = pool[Math.floor(Math.random() * pool.length)];
    const colors = sel.colors || [];
    if (colors.length) bm.previewPick[f + ":color"] = colors[Math.floor(Math.random() * colors.length)];
    else delete bm.previewPick[f + ":color"];
  });
}

function bmRenderValue(feature, id) {
  const rp = bm.renderParams[feature];
  if (!rp) return null;
  if (rp.color) { const n = parseInt(String(id).replace("#", ""), 16); return isNaN(n) ? null : String(n); }
  return String(id);
}

function bmColorParam(feature) {
  const colorParamMap = { "top_tone1": "top", "bottom_tone1": "bottom", "bottom": "dress", "footwear_tone": "footwear", "headwear_tone": "headwear", "outerwear_tone": "outerwear", "outfit_tone": "outfit" };
  return null;
}

function buildAvatarUrl() {
  if (!bm.baseAvatar) return "";
  let url; try { url = new URL(bm.baseAvatar); } catch (e) { return ""; }
  const p = url.searchParams;
  p.set("scale", "1");  // lighter render — preview re-fetches on every change
  const preset = bm.presets[bm.current] || {};
  Object.keys(preset).forEach(k => p.set(k, preset[k]));
  const cfg = bm.models[bm.current] || {};
  bm.order.forEach(f => {
    const rp = bm.renderParams[f]; const sel = cfg[f];
    if (!rp) return;
    let id = null, color = null;
    if (sel && sel.mode === "fixed") {
      id = sel.id; color = sel.color;
    } else if (sel && sel.mode === "random") {
      const pool = sel.pool || [];
      if (pool.length) id = (bm.previewPick[f] && pool.includes(bm.previewPick[f])) ? bm.previewPick[f] : pool[0];
      const colors = sel.colors || [];
      if (colors.length) color = (bm.previewPick[f + ":color"] && colors.includes(bm.previewPick[f + ":color"])) ? bm.previewPick[f + ":color"] : colors[0];
    }
    // Preset/unconfigured features inherit the model preset already applied above.
    if (id) { const v = bmRenderValue(f, id); if (v != null) p.set(rp.param, v); }
    if (color) {
      // Outfit colors are #hex swatches but the *_tone1 render param wants a decimal.
      const toneParam = rp.param + "_tone1";
      const cv = /^#?[0-9a-fA-F]{6}$/.test(String(color)) ? String(parseInt(String(color).replace("#", ""), 16)) : String(color);
      if (cv && cv !== "NaN") p.set(toneParam, cv);
    }
  });
  return url.toString();
}

function renderAvatar() {
  const u = buildAvatarUrl();
  if (u) el("bm-avatar").src = u;
}

el("bm-model").addEventListener("change", e => { bm.current = e.target.value; bm.previewPick = {}; renderBitmojiAll(); });

el("bm-catbar").addEventListener("click", e => {
  const groupBtn = e.target.closest(".bm-cat-group-btn");
  if (groupBtn) {
    const g = groupBtn.dataset.group;
    if (bm.openGroups.has(g)) bm.openGroups.delete(g);
    else { bm.openGroups.clear(); bm.openGroups.add(g); }  // accordion: close others
    renderCatBar();
    return;
  }
  const cat = e.target.closest(".bm-cat"); if (!cat) return;
  bm.active = cat.dataset.feature;
  const g = bm.featGroup[bm.active];
  if (g) { bm.openGroups.clear(); bm.openGroups.add(g); }
  renderCatBar(); renderSide();
});

document.getElementById("bm-mode-group").addEventListener("click", e => {
  const btn = e.target.closest(".bm-mode-btn"); if (!btn) return;
  const mode = btn.dataset.mode; const cfg = modelCfg(); const f = bm.active;
  if (mode === "preset") delete cfg[f];
  else if (mode === "fixed") cfg[f] = { mode: "fixed", id: (cfg[f] && cfg[f].id) || "" };
  else cfg[f] = { mode: "random", pool: (cfg[f] && cfg[f].pool) || [] };
  renderCatBar(); renderSide(); renderAvatar();
});

el("bm-options").addEventListener("click", e => {
  const swatchBtn = e.target.closest(".bm-opt-swatch");
  if (swatchBtn) {
    const f = bm.active; const color = swatchBtn.dataset.color; const sel = modelCfg()[f];
    if (!sel) return;
    if (sel.mode === "fixed") {
      sel.color = color;
    } else if (sel.mode === "random") {
      sel.colors = sel.colors || [];
      const ci = sel.colors.indexOf(color);
      if (ci >= 0) sel.colors.splice(ci, 1); else sel.colors.push(color);
    }
    el("bm-options").querySelectorAll(".bm-opt-swatch").forEach(b => b.classList.toggle("sel", b.dataset.color === color));
    renderAvatar();
    return;
  }
  const optBtn = e.target.closest(".bm-opt"); if (!optBtn || optBtn.classList.contains("bm-opt-swatch")) return;
  const f = bm.active; const id = optBtn.dataset.id; const sel = modelCfg()[f];
  if (!sel) return;
  if (sel.mode === "fixed") {
    sel.id = id;
    el("bm-options").querySelectorAll(".bm-opt").forEach(b => b.classList.toggle("sel", b.dataset.id === id));
  } else if (sel.mode === "random") {
    sel.pool = sel.pool || [];
    const i = sel.pool.indexOf(id);
    if (i >= 0) sel.pool.splice(i, 1); else sel.pool.push(id);
    optBtn.classList.toggle("sel");
    bm.previewPick[f] = id;
  }
  renderAvatar();
});

el("bm-shuffle").addEventListener("click", () => {
  shufflePreviewPicks();
  renderAvatar();
});

el("bm-save").addEventListener("click", async () => {
  el("bm-status").textContent = "Saving…";
  try {
    const r = await fetch(NYX_BASE + "/bitmoji/models", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...tokenHeaders() },
      body: JSON.stringify({ models: bm.models, token: TOKEN }),
    });
    const d = await r.json().catch(() => ({}));
    if (d.ok) { bm.models = d.models || bm.models; el("bm-status").textContent = "Saved."; toast("Nyxmoji config saved.", true); renderBitmojiAll(); }
    else { el("bm-status").textContent = d.error || "Save failed."; toast(d.error || "Save failed.", false); }
  } catch (e) { el("bm-status").textContent = "Save failed: " + e; toast("Save failed.", false); }
});

el("bm-export").addEventListener("click", () => {
  const blob = new Blob([JSON.stringify(bm.models, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "bitmoji_models.json";
  a.click();
  URL.revokeObjectURL(a.href);
  toast("Exported bitmoji_models.json", true);
});

el("bm-import").addEventListener("click", () => el("bm-import-file").click());
el("bm-import-file").addEventListener("change", e => {
  const file = e.target.files && e.target.files[0]; if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    try {
      const parsed = JSON.parse(reader.result);
      if (!parsed || typeof parsed !== "object") throw new Error("not an object");
      bm.models = parsed; bm.previewPick = {};
      renderBitmojiModels(); renderBitmojiAll();
      el("bm-status").textContent = "Imported — review and click Save to apply.";
      toast("Config imported. Click Save to apply.", true);
    } catch (err) { toast("Import failed: invalid JSON.", false); }
  };
  reader.readAsText(file);
  e.target.value = "";
});

connect();
render();
// Auto-check for updates on launch so the indicator lights up without the user
// having to open Settings. Best-effort — silent when offline or unconfigured.
setTimeout(() => { runUpdateCheck(false).catch(() => {}); }, 1200);

// Deep link: the extension's "Setup & Install" button opens the dashboard at
// #setup — jump to Settings and highlight the Setup & Install card.
function handleHashRoute() {
  if (location.hash === "#nyx") { setActive("nyx"); return; }
  if (location.hash === "#nyxify") { setActive("nyxify"); return; }
  if (location.hash === "#setup") {
    setActive("settings");
    setTimeout(() => {
      const card = el("card-setup");
      if (card) {
        card.scrollIntoView({ behavior: "smooth", block: "center" });
        card.classList.add("flash");
        setTimeout(() => card.classList.remove("flash"), 1800);
      }
    }, 120);
  }
}
window.addEventListener("hashchange", handleHashRoute);
handleHashRoute();
