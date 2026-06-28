let latestQueueRows = [];
let latestScrapeStatus = null;
let selectedRowKey = "";
let renderedQueueSignature = "";
let renderedScrapeSignature = "";
let popupLivePort = null;
let popupLiveReconnectTimer = null;
let scrapeInputSaveTimer = null;

const POPUP_VIEW_STORAGE_KEY = "nyxifyPopupView";
const POPUP_CONFIG_STORAGE_KEY = "nyxifyConfig";
const POPUP_AUTO_FILL_PROGRESS_STORAGE_KEY = "nyxifyAutoFillAccountProgress";
const DEFAULT_TEMPORARY_PROFILE_NAME = "Snapchat:";
const DEFAULT_ADSPOWER_GROUP = "Snapchat";
const DEFAULT_TAG_ONE = "Snapchat";

function normalizePositiveInteger(value, fallback = 0) {
  const parsed = parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function normalizePopupConfig(config) {
  const safeConfig = config || {};
  return {
    enabled: safeConfig.enabled !== false,
    pushAdspowerIdEnabled: safeConfig.pushAdspowerIdEnabled !== false,
    fullAutoModeEnabled: safeConfig.fullAutoModeEnabled === true,
    autoFillRow: safeConfig.autoFillRow === true,
    lockG5: safeConfig.lockG5 === true,
    temporaryProfileName: String(safeConfig.temporaryProfileName || DEFAULT_TEMPORARY_PROFILE_NAME),
    adspowerGroup: String(safeConfig.adspowerGroup || DEFAULT_ADSPOWER_GROUP),
    tagOne: String(safeConfig.tagOne || DEFAULT_TAG_ONE),
    tagTwo: String(safeConfig.tagTwo || ""),
    adspowerTagsEnabled: safeConfig.adspowerTagsEnabled !== false,
    rowLimit: normalizePositiveInteger(safeConfig.rowLimit, 20),
    autoFillAccountTarget: normalizePositiveInteger(safeConfig.autoFillAccountTarget, 0),
    bannedProxies: Array.isArray(safeConfig.bannedProxies) ? safeConfig.bannedProxies : [],
  };
}

function setPrimaryStatus(message, holdMs = 0) {
  const statusLine = document.getElementById("statusLine");
  if (!statusLine) {
    return;
  }

  statusLine.textContent = String(message || "");
  statusLine.dataset.holdUntil = holdMs > 0 ? String(Date.now() + holdMs) : "0";
}

function applyPrimaryStatus(message) {
  const statusLine = document.getElementById("statusLine");
  if (!statusLine) {
    return;
  }

  const holdUntil = Number(statusLine.dataset.holdUntil || 0);
  if (holdUntil > Date.now()) {
    return;
  }

  statusLine.textContent = String(message || "");
}

function getQueueSignature(rows) {
  return JSON.stringify((rows || []).map((row) => [
    String(row.row_key || "").trim(),
    String(row.model || ""),
    String(row.ip_address || ""),
    String(row.proxy_address || ""),
    String(row.adspower_profile_id || ""),
    String(row.status || ""),
  ]));
}

function syncSelectedRowClass() {
  document.querySelectorAll(".queue-table-row").forEach((element) => {
    const isSelected = String(element.dataset.rowKey || "").trim() === selectedRowKey;
    element.classList.toggle("queue-table-row-selected", isSelected);
  });
}

function setInputValue(id, value) {
  const element = document.getElementById(id);
  if (!element) {
    return;
  }
  if (document.activeElement === element) {
    return;
  }
  const nextValue = value == null ? "" : String(value);
  if (element.value !== nextValue) {
    element.value = nextValue;
  }
}

function setTextAreaValue(id, value) {
  setInputValue(id, value);
}

function setElementText(id, value) {
  const element = document.getElementById(id);
  if (!element) {
    return;
  }
  const nextValue = value == null ? "" : String(value);
  if (element.textContent !== nextValue) {
    element.textContent = nextValue;
  }
}

function getRunnerStateKey(runnerStatus) {
  if (!runnerStatus || runnerStatus.loading === true || runnerStatus.unavailable === true) {
    return "offline";
  }
  const bot = runnerStatus.bot || {};
  const rawState = String(bot.state || "stopped").trim().toLowerCase();
  return ["running", "paused", "waiting", "stopped"].includes(rawState) ? rawState : "stopped";
}

function updateRunnerActionButtons(runnerStatus) {
  const startStopButton = document.getElementById("startStopRunnerButton");
  const pauseResumeButton = document.getElementById("pauseResumeRunnerButton");
  if (!startStopButton || !pauseResumeButton) {
    return;
  }

  const stateKey = getRunnerStateKey(runnerStatus);
  const isOffline = stateKey === "offline";
  const isActive = ["running", "waiting", "paused"].includes(stateKey);
  const isPaused = stateKey === "paused";
  const startStopAction = isActive ? "stop" : "start";
  const pauseResumeAction = isPaused ? "resume" : "pause";

  startStopButton.dataset.action = startStopAction;
  startStopButton.textContent = startStopAction === "stop" ? "Stop" : "Start";
  startStopButton.title = startStopAction === "stop" ? "Stop Nyxify runner" : "Start Nyxify runner";
  startStopButton.disabled = isOffline;
  startStopButton.classList.toggle("runner-action-stop-active", startStopAction === "stop");

  pauseResumeButton.dataset.action = pauseResumeAction;
  pauseResumeButton.textContent = pauseResumeAction === "resume" ? "Resume" : "Pause";
  pauseResumeButton.title = pauseResumeAction === "resume" ? "Resume Nyxify runner" : "Pause Nyxify runner";
  pauseResumeButton.disabled = isOffline;
  pauseResumeButton.classList.toggle("runner-action-resume-active", pauseResumeAction === "resume");
}

function renderSheetQueue(rows) {
  const container = document.getElementById("sheetQueue");
  if (!container) {
    return;
  }

  if (!rows || !rows.length) {
    selectedRowKey = "";
    renderedQueueSignature = "";
    container.innerHTML = '<div class="queue-table-empty">No Nyxify queue rows found.</div>';
    return;
  }

  if (!rows.some((row) => String(row.row_key || "").trim() === selectedRowKey)) {
    selectedRowKey = String(rows[0].row_key || "").trim();
  }

  const nextSignature = getQueueSignature(rows);
  if (nextSignature === renderedQueueSignature) {
    syncSelectedRowClass();
    return;
  }

  const header = `
    <div class="queue-table-header">
      <div class="queue-cell">Model</div>
      <div class="queue-cell">IP</div>
      <div class="queue-cell">Proxy</div>
      <div class="queue-cell">AdsPower ID</div>
      <div class="queue-cell">Status</div>
    </div>
  `;

  const rowsHtml = rows.map((row) => {
    const rowKey = String(row.row_key || "").trim();
    const selectedClass = rowKey === selectedRowKey ? " queue-table-row-selected" : "";
    return `
      <div class="queue-table-row${selectedClass}" data-row-key="${rowKey}">
        <div class="queue-cell" data-label="Model">${String(row.model || "-")}</div>
        <div class="queue-cell" data-label="IP">${String(row.ip_address || "-")}</div>
        <div class="queue-cell" data-label="Proxy">${String(row.proxy_address || "-")}</div>
        <div class="queue-cell" data-label="AdsPower ID">${String(row.adspower_profile_id || "-")}</div>
        <div class="queue-cell" data-label="Status">${String(row.status || "-")}</div>
      </div>
    `;
  }).join("");

  container.innerHTML = header + rowsHtml;
  renderedQueueSignature = nextSignature;
}

function getScrapeEntriesByStatus(results, statuses) {
  const allowed = new Set((statuses || []).map((status) => String(status || "").trim().toLowerCase()));
  return (results || []).filter((entry) => allowed.has(String(entry && entry.status || "").trim().toLowerCase()));
}

function formatScrapeUsernames(entries) {
  return (entries || []).map((entry) => String(entry && entry.username || "").trim()).filter(Boolean).join("\n");
}

function renderScrapeSnapshot(scrapeStatus) {
  const safeStatus = scrapeStatus || {};
  const config = safeStatus.config || {};
  const results = Array.isArray(safeStatus.scrapeResults) ? safeStatus.scrapeResults : [];
  const eventLog = Array.isArray(safeStatus.eventLog) ? safeStatus.eventLog : [];
  const runnerState = safeStatus.runnerState || {};
  const inputText = String(safeStatus.inputText || "");
  const inputCount = Number(safeStatus.inputCount || 0);
  const checkedCount = results.length;
  const withAccountEntries = getScrapeEntriesByStatus(results, ["no_bitmoji", "has_bitmoji"]);
  const noAccountEntries = getScrapeEntriesByStatus(results, ["not_found"]);
  const unknownEntries = getScrapeEntriesByStatus(results, ["unknown"]);
  const runnerStatus = String(runnerState.status || "idle");
  const isRunning = runnerStatus === "running";
  const currentUsername = String(runnerState.current_username || "").trim();
  const nextSignature = JSON.stringify({
    config: {
      maxParallelTabs: config.maxParallelTabs || 4,
      profileTimeoutMs: config.profileTimeoutMs || 12000,
    },
    inputText,
    inputCount,
    runnerStatus,
    activeCount: Number(runnerState.active_count || 0),
    completed: Number(runnerState.completed || 0),
    total: Number(runnerState.total || inputCount || 0),
    currentUsername,
    results: results.map((entry) => [
      String(entry && entry.username || ""),
      String(entry && entry.status || ""),
      String(entry && entry.checked_at || ""),
    ]),
    eventLog: eventLog.map((entry) => [
      String(entry && entry.at || ""),
      String(entry && entry.message || ""),
    ]),
  });

  latestScrapeStatus = safeStatus;
  if (nextSignature === renderedScrapeSignature) {
    return;
  }
  renderedScrapeSignature = nextSignature;

  setInputValue("scrapeParallelTabsInput", config.maxParallelTabs || 4);
  setInputValue("scrapeTimeoutMsInput", config.profileTimeoutMs || 12000);
  setTextAreaValue("scrapeInputText", inputText);

  setElementText("scrapeStatusLine", isRunning
    ? `Checking ${Number(runnerState.completed || 0)} / ${Number(runnerState.total || inputCount || 0)} username(s).`
    : checkedCount
      ? `Checked ${checkedCount} username(s).`
      : "Paste usernames and click Check.");
  setElementText("scrapeRunnerLine", `State: ${runnerStatus} | Active tabs: ${Number(runnerState.active_count || 0)}${currentUsername ? ` | Current: ${currentUsername}` : ""}`);

  setElementText("scrapeInputCount", String(inputCount));
  setElementText("scrapeCheckedCount", String(checkedCount));
  setElementText("scrapeWithAccountCount", String(withAccountEntries.length));
  setElementText("scrapeNoAccountCount", String(noAccountEntries.length));
  setElementText("scrapeUnknownCount", String(unknownEntries.length));

  setElementText("withAccountBadge", String(withAccountEntries.length));
  setElementText("noAccountBadge", String(noAccountEntries.length));
  setElementText("unknownBadge", String(unknownEntries.length));

  setTextAreaValue("withAccountResults", formatScrapeUsernames(withAccountEntries));
  setTextAreaValue("noAccountResults", formatScrapeUsernames(noAccountEntries));
  setTextAreaValue("unknownResults", formatScrapeUsernames(unknownEntries));

  setElementText("scrapeEventLog", eventLog.length
    ? eventLog.map((entry) => {
        const at = entry && entry.at ? new Date(entry.at).toLocaleString() : "-";
        return `[${at}] ${String(entry && entry.message || "").trim()}`;
      }).join("\n")
    : "No scrape events yet.");
}

function applyPopupStatusSnapshot(status) {
  const safeStatus = status || {};
  const config = safeStatus.config || {};
  const runnerStatus = safeStatus.runnerStatus || {};
  const runnerLoading = runnerStatus.loading === true;
  const counts = runnerStatus.counts || {};
  const bot = runnerStatus.bot || {};
  const lastSeenEntries = safeStatus.lastSeenEntries || [];
  const lastSync = safeStatus.lastSync || null;
  const autoFillProgress = safeStatus.autoFillProgress || {};
  const autoFillTarget = Number(config.autoFillAccountTarget || 0);
  const autoFillCount = Number(autoFillProgress.count || 0);
  updateRunnerActionButtons(runnerStatus);

  document.getElementById("popupPushAdspowerIdToggle").checked = config.pushAdspowerIdEnabled !== false;
  document.getElementById("popupAdspowerTagsToggle").checked = config.adspowerTagsEnabled !== false;
  document.getElementById("popupFullAutoModeToggle").checked = config.fullAutoModeEnabled === true;
  document.getElementById("popupAutoFillRowToggle").checked = config.autoFillRow === true;
  document.getElementById("popupLockG5Toggle").checked = config.lockG5 === true;
  document.getElementById("countReady").textContent = String(counts.ready || 0);
  document.getElementById("countWaiting").textContent = String(counts.waiting || 0);
  document.getElementById("countRunning").textContent = String(counts.running || 0);
  document.getElementById("countFailed").textContent = String(counts.failed || 0);
  document.getElementById("countDone").textContent = String(counts.done || 0);
  setInputValue("popupTemporaryName", config.temporaryProfileName);
  setInputValue("popupGroup", config.adspowerGroup);
  setInputValue("popupTagOne", config.tagOne);
  setInputValue("popupTagTwo", config.tagTwo || "");
  setInputValue("popupRowLimit", config.rowLimit || 20);
  setInputValue("popupAutoFillAccountTarget", autoFillTarget > 0 ? autoFillTarget : "");
  setElementText(
    "popupAutoFillTargetStatus",
    autoFillTarget > 0
      ? `Auto-fill target: ${Math.min(autoFillCount, autoFillTarget)} / ${autoFillTarget}`
      : "Unlimited"
  );

  const banned = Array.isArray(config.bannedProxies) ? config.bannedProxies : [];
  setTextAreaValue("popupBlockedProxies", banned.join("\n"));
  const countLabel = document.getElementById("popupBlockedProxiesCount");
  if (countLabel) {
    countLabel.textContent = banned.length
      ? `${banned.length} banned ${banned.length === 1 ? "proxy" : "proxies"}.`
      : "No proxies are banned.";
  }

  applyPrimaryStatus(
    config.enabled === false
      ? "Nyxify is off."
      : runnerLoading
        ? "Nyxify settings loaded. Checking runner..."
        : `${counts.pending || 0} pending row(s) in Nyxify runner.`
  );
  document.getElementById("runnerLine").textContent = bot.detail || (runnerLoading ? "Checking Nyxify runner..." : "Nyxify runner unavailable.");
  const adspowerUsage = runnerStatus.adspower_usage || {};
  const usedProfiles = Number.isFinite(Number(adspowerUsage.used)) ? Number(adspowerUsage.used) : null;
  const usageError = String(adspowerUsage.error || "").trim();
  document.getElementById("capacityLine").textContent = usedProfiles != null
    ? `AdsPower profiles used: ${usedProfiles}.`
    : usageError || (runnerLoading ? "Checking AdsPower profile usage..." : "AdsPower profile usage unavailable.");
  document.getElementById("lastSeen").textContent = lastSeenEntries.length
    ? lastSeenEntries.map((entry) => `${entry.model} | ${entry.ip_address}`).join("\n")
    : "No dashboard rows detected yet.";
  document.getElementById("syncLine").textContent = !lastSync
    ? "No sync has run yet."
    : `${lastSync.failed ? "Last sync failed" : "Last sync ok"} at ${new Date(lastSync.syncedAt).toLocaleString()}${lastSync.message ? `: ${lastSync.message}` : ""}`;

  if (!runnerLoading || (Array.isArray(runnerStatus.rows) && runnerStatus.rows.length)) {
    latestQueueRows = runnerStatus.rows || [];
  }
  renderSheetQueue(latestQueueRows);
  if (Object.prototype.hasOwnProperty.call(safeStatus, "scrapeStatus")) {
    renderScrapeSnapshot(safeStatus.scrapeStatus || {});
  }
}

function applyStoredSettingsSnapshot() {
  chrome.storage.sync.get(POPUP_CONFIG_STORAGE_KEY, (syncData) => {
    const config = normalizePopupConfig(syncData && syncData[POPUP_CONFIG_STORAGE_KEY]);
    chrome.storage.local.get(POPUP_AUTO_FILL_PROGRESS_STORAGE_KEY, (localData) => {
      applyPopupStatusSnapshot({
        config,
        autoFillProgress: (localData && localData[POPUP_AUTO_FILL_PROGRESS_STORAGE_KEY]) || {},
        runnerStatus: {
          loading: true,
          counts: {},
          rows: latestQueueRows,
          bot: {
            detail: "Checking Nyxify runner...",
          },
          adspower_usage: {},
        },
        lastSeenEntries: [],
        lastSync: null,
      });
    });
  });
}

function refreshPopupStatus(statusMessage, force = false) {
  if (statusMessage) {
    setPrimaryStatus(statusMessage, 1500);
  }

  chrome.runtime.sendMessage({ type: "NYXIFY_GET_STATUS", force }, (response) => {
    if (!response || !response.ok) {
      setPrimaryStatus((response && response.error) || "Could not load Nyxify status.", 2500);
      return;
    }

    applyPopupStatusSnapshot(response.status || {});
  });
}

function savePopupSettings() {
  chrome.runtime.sendMessage({
    type: "NYXIFY_SAVE_CONFIG",
    enabled: true,
    pushAdspowerIdEnabled: document.getElementById("popupPushAdspowerIdToggle").checked,
    adspowerTagsEnabled: document.getElementById("popupAdspowerTagsToggle").checked,
    fullAutoModeEnabled: document.getElementById("popupFullAutoModeToggle").checked,
    autoFillRow: document.getElementById("popupAutoFillRowToggle").checked,
    lockG5: document.getElementById("popupLockG5Toggle").checked,
    temporaryProfileName: document.getElementById("popupTemporaryName").value,
    adspowerGroup: document.getElementById("popupGroup").value,
    tagOne: document.getElementById("popupTagOne").value,
    tagTwo: document.getElementById("popupTagTwo").value,
    rowLimit: document.getElementById("popupRowLimit").value,
    autoFillAccountTarget: document.getElementById("popupAutoFillAccountTarget").value,
  }, (response) => {
    if (!response || !response.ok) {
      setPrimaryStatus((response && response.error) || "Could not save Nyxify settings.", 2500);
      return;
    }
    refreshPopupStatus("Nyxify settings saved.");
  });
}

function saveDashboardToggle(toggleId, configKey, enabledMessage, disabledMessage) {
  const toggle = document.getElementById(toggleId);
  if (!toggle) {
    return;
  }

  const checked = toggle.checked;
  const payload = { type: "NYXIFY_SAVE_CONFIG" };
  payload[configKey] = checked;
  setPrimaryStatus(checked ? enabledMessage : disabledMessage, 1500);

  chrome.runtime.sendMessage(payload, (response) => {
    if (!response || !response.ok) {
      toggle.checked = !checked;
      setPrimaryStatus((response && response.error) || "Could not save Nyxify toggle.", 2500);
      return;
    }
    refreshPopupStatus(checked ? enabledMessage : disabledMessage, true);
  });
}

function runBotAction(action, loadingMessage, fallbackMessage) {
  setPrimaryStatus(loadingMessage, 2000);
  chrome.runtime.sendMessage({ type: "NYXIFY_BOT_ACTION", action }, (response) => {
    if (!response || !response.ok) {
      setPrimaryStatus((response && response.error) || "Nyxify action failed.", 2500);
      return;
    }
    refreshPopupStatus((response.payload && response.payload.message) || fallbackMessage);
  });
}

function scheduleLiveStatusReconnect() {
  if (popupLiveReconnectTimer) {
    window.clearTimeout(popupLiveReconnectTimer);
  }
  popupLiveReconnectTimer = window.setTimeout(() => {
    popupLiveReconnectTimer = null;
    connectLiveStatus();
  }, 600);
}

function connectLiveStatus() {
  if (popupLivePort) {
    return;
  }

  try {
    popupLivePort = chrome.runtime.connect({ name: "nyxify-popup-live" });
  } catch (_error) {
    scheduleLiveStatusReconnect();
    return;
  }

  popupLivePort.onMessage.addListener((message) => {
    if (!message) {
      return;
    }
    if (message.type === "status") {
      applyPopupStatusSnapshot(message.status || {});
      return;
    }
    if (message.type === "status-error") {
      applyPrimaryStatus(message.error || "Could not load Nyxify status.");
    }
  });

  popupLivePort.onDisconnect.addListener(() => {
    popupLivePort = null;
    if (!document.hidden) {
      scheduleLiveStatusReconnect();
    }
  });
}

function getSelectedRow() {
  return latestQueueRows.find((row) => String(row.row_key || "").trim() === selectedRowKey) || null;
}

function setActivePopupView(viewId) {
  const normalizedViewId = viewId === "scrapeView" ? "scrapeView" : "runnerView";
  document.querySelectorAll(".popup-tab").forEach((button) => {
    const isActive = String(button.dataset.view || "") === normalizedViewId;
    button.classList.toggle("popup-tab-active", isActive);
    button.setAttribute("aria-selected", isActive ? "true" : "false");
  });
  document.querySelectorAll(".popup-view").forEach((view) => {
    const isActive = view.id === normalizedViewId;
    view.classList.toggle("popup-view-active", isActive);
    view.hidden = !isActive;
  });
  window.localStorage.setItem(POPUP_VIEW_STORAGE_KEY, normalizedViewId);
}

function getScrapeConfigPayloadFromInputs() {
  return {
    maxParallelTabs: document.getElementById("scrapeParallelTabsInput").value,
    profileTimeoutMs: document.getElementById("scrapeTimeoutMsInput").value,
  };
}

function saveScrapeInputSilently() {
  chrome.runtime.sendMessage({
    type: "NYXIFY_SCRAPE_SAVE_INPUT",
    inputText: document.getElementById("scrapeInputText").value,
  }, () => {});
}

function saveScrapeConfigSilently() {
  chrome.runtime.sendMessage({
    type: "NYXIFY_SCRAPE_SAVE_CONFIG",
    config: getScrapeConfigPayloadFromInputs(),
  }, () => {});
}

function queueScrapeInputSave() {
  if (scrapeInputSaveTimer) {
    window.clearTimeout(scrapeInputSaveTimer);
  }
  scrapeInputSaveTimer = window.setTimeout(() => {
    scrapeInputSaveTimer = null;
    saveScrapeInputSilently();
  }, 250);
}

function startUsernameScrape() {
  const inputText = document.getElementById("scrapeInputText").value;
  document.getElementById("scrapeStatusLine").textContent = "Starting username scrape...";
  chrome.runtime.sendMessage({
    type: "NYXIFY_SCRAPE_START",
    inputText,
    config: getScrapeConfigPayloadFromInputs(),
  }, (response) => {
    if (!response || !response.ok) {
      document.getElementById("scrapeStatusLine").textContent = (response && response.error) || "Could not start username scrape.";
      return;
    }
    refreshPopupStatus("Username scrape started.", true);
  });
}

function stopUsernameScrape() {
  document.getElementById("scrapeStatusLine").textContent = "Stopping username scrape...";
  chrome.runtime.sendMessage({ type: "NYXIFY_SCRAPE_STOP" }, (response) => {
    if (!response || !response.ok) {
      document.getElementById("scrapeStatusLine").textContent = (response && response.error) || "Could not stop username scrape.";
      return;
    }
    refreshPopupStatus("Username scrape stopped.", true);
  });
}

function clearUsernameScrape() {
  document.getElementById("scrapeStatusLine").textContent = "Clearing username scrape data...";
  chrome.runtime.sendMessage({ type: "NYXIFY_SCRAPE_CLEAR" }, (response) => {
    if (!response || !response.ok) {
      document.getElementById("scrapeStatusLine").textContent = (response && response.error) || "Could not clear username scrape data.";
      return;
    }
    refreshPopupStatus("Username scrape data cleared.", true);
  });
}

async function copyScrapeResults(statuses, emptyMessage, successMessage) {
  const results = latestScrapeStatus && Array.isArray(latestScrapeStatus.scrapeResults)
    ? latestScrapeStatus.scrapeResults
    : [];
  const output = formatScrapeUsernames(getScrapeEntriesByStatus(results, statuses));
  const statusLine = document.getElementById("scrapeStatusLine");
  if (!output) {
    statusLine.textContent = emptyMessage;
    return;
  }

  try {
    await navigator.clipboard.writeText(output);
    statusLine.textContent = successMessage;
  } catch (_error) {
    statusLine.textContent = "Could not copy usernames.";
  }
}

// Nyxify is always enabled now — the NyxSuite (bridge) toggle is the master
// switch. Heal any previously-disabled state so detection always runs.
chrome.runtime.sendMessage({ type: "NYXIFY_SET_ENABLED", enabled: true }, () => {});

[
  ["popupPushAdspowerIdToggle", "pushAdspowerIdEnabled", "Push AdsPower ID enabled.", "Push AdsPower ID disabled."],
  ["popupFullAutoModeToggle", "fullAutoModeEnabled", "Full Auto Mode enabled.", "Full Auto Mode disabled."],
  ["popupAutoFillRowToggle", "autoFillRow", "Auto-Fill Row enabled.", "Auto-Fill Row disabled."],
  ["popupLockG5Toggle", "lockG5", "Lock in G5 enabled.", "Lock in G5 disabled."],
].forEach(([toggleId, configKey, enabledMessage, disabledMessage]) => {
  const toggle = document.getElementById(toggleId);
  if (!toggle) {
    return;
  }
  toggle.addEventListener("change", () => {
    saveDashboardToggle(toggleId, configKey, enabledMessage, disabledMessage);
  });
});

document.getElementById("startStopRunnerButton").addEventListener("click", (event) => {
  const action = event.currentTarget.dataset.action === "stop" ? "stop" : "start";
  runBotAction(
    action,
    action === "stop" ? "Stopping Nyxify runner..." : "Starting Nyxify runner...",
    action === "stop" ? "Nyxify runner stopped." : "Nyxify runner started."
  );
});
document.getElementById("pauseResumeRunnerButton").addEventListener("click", (event) => {
  const action = event.currentTarget.dataset.action === "resume" ? "resume" : "pause";
  runBotAction(
    action,
    action === "resume" ? "Resuming Nyxify runner..." : "Pausing Nyxify runner...",
    action === "resume" ? "Nyxify runner resumed." : "Nyxify runner paused."
  );
});
document.getElementById("refreshButton").addEventListener("click", () => {
  refreshPopupStatus("Refreshing Nyxify queue...", true);
  if (popupLivePort) {
    try {
      popupLivePort.postMessage({ type: "refresh" });
    } catch (_error) {
    }
  }
});
document.getElementById("resetFailedButton").addEventListener("click", () => {
  runBotAction("reset_failed", "Resetting failed Nyxify rows...", "Failed Nyxify rows reset.");
});
document.getElementById("deleteOrphanProfilesButton").addEventListener("click", () => {
  runBotAction(
    "delete_orphan_failed_profiles",
    "Deleting orphan failed profiles...",
    "Orphan failed profile cleanup finished."
  );
});
document.getElementById("clearQueueButton").addEventListener("click", () => {
  runBotAction("clear_queue", "Clearing Nyxify queue...", "Nyxify queue cleared.");
});
document.getElementById("savePopupSettingsButton").addEventListener("click", savePopupSettings);

document.getElementById("savePopupBlockedProxiesButton").addEventListener("click", () => {
  const raw = document.getElementById("popupBlockedProxies").value || "";
  const bannedProxies = raw.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  chrome.runtime.sendMessage({
    type: "NYXIFY_SAVE_CONFIG",
    bannedProxies,
  }, (response) => {
    if (!response || !response.ok) {
      setPrimaryStatus((response && response.error) || "Could not save banned proxies.", 2500);
      return;
    }
    refreshPopupStatus(
      bannedProxies.length
        ? `Saved ${bannedProxies.length} banned proxy pattern(s).`
        : "Banned proxy list cleared.",
      true
    );
  });
});

document.getElementById("clearPopupBlockedProxiesButton").addEventListener("click", () => {
  document.getElementById("popupBlockedProxies").value = "";
  chrome.runtime.sendMessage({
    type: "NYXIFY_SAVE_CONFIG",
    bannedProxies: [],
  }, (response) => {
    if (!response || !response.ok) {
      setPrimaryStatus((response && response.error) || "Could not clear banned proxies.", 2500);
      return;
    }
    refreshPopupStatus("Banned proxy list cleared.", true);
  });
});
document.getElementById("banProxyButton").addEventListener("click", () => {
  const row = getSelectedRow();
  if (!row || !(row.proxy_address || row.ip_address)) {
    setPrimaryStatus("Select a row with a proxy first.", 2500);
    return;
  }

  chrome.runtime.sendMessage({
    type: "NYXIFY_BAN_PROXY",
    proxyValue: row.proxy_address || row.ip_address,
  }, (response) => {
    if (!response || !response.ok) {
      setPrimaryStatus((response && response.error) || "Could not ban proxy.", 2500);
      return;
    }
    refreshPopupStatus(`Banned proxy ${row.proxy_address || row.ip_address}.`);
  });
});

document.getElementById("removeQueueRowButton").addEventListener("click", () => {
  const row = getSelectedRow();
  if (!row) {
    setPrimaryStatus("Select a queue row first.", 2500);
    return;
  }

  chrome.runtime.sendMessage({
    type: "NYXIFY_REMOVE_QUEUE_ROW",
    rowKey: row.row_key,
  }, (response) => {
    if (!response || !response.ok) {
      setPrimaryStatus((response && response.error) || "Could not remove Nyxify row.", 2500);
      return;
    }
    refreshPopupStatus(`Removed ${row.model} | ${row.ip_address}.`);
  });
});

document.getElementById("sheetQueue").addEventListener("click", (event) => {
  const row = event.target && event.target.closest(".queue-table-row");
  if (!row) {
    return;
  }
  selectedRowKey = String(row.dataset.rowKey || "").trim();
  syncSelectedRowClass();
});

document.querySelectorAll(".popup-tab").forEach((button) => {
  button.addEventListener("click", () => {
    setActivePopupView(String(button.dataset.view || "runnerView"));
  });
});

document.getElementById("scrapeInputText").addEventListener("input", queueScrapeInputSave);
document.getElementById("scrapeParallelTabsInput").addEventListener("change", saveScrapeConfigSilently);
document.getElementById("scrapeTimeoutMsInput").addEventListener("change", saveScrapeConfigSilently);
document.getElementById("scrapeCheckButton").addEventListener("click", startUsernameScrape);
document.getElementById("scrapeStopButton").addEventListener("click", stopUsernameScrape);
document.getElementById("scrapeClearButton").addEventListener("click", clearUsernameScrape);
document.getElementById("copyWithAccountButton").addEventListener("click", () => {
  copyScrapeResults(["no_bitmoji", "has_bitmoji"], "No usernames with account yet.", "Copied usernames with account.");
});
document.getElementById("copyNoAccountButton").addEventListener("click", () => {
  copyScrapeResults(["not_found"], "No no-account usernames yet.", "Copied usernames with no account.");
});
document.getElementById("scrapeOpenPageButton").addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "NYXIFY_SCRAPE_OPEN_PAGE" }, (response) => {
    if (!response || !response.ok) {
      document.getElementById("scrapeStatusLine").textContent = (response && response.error) || "Could not open username scrape page.";
    }
  });
});

document.addEventListener("visibilitychange", () => {
  if (!document.hidden) {
    connectLiveStatus();
    refreshPopupStatus("Refreshing Nyxify queue...", true);
  }
});

window.addEventListener("beforeunload", () => {
  if (popupLiveReconnectTimer) {
    window.clearTimeout(popupLiveReconnectTimer);
    popupLiveReconnectTimer = null;
  }
  if (scrapeInputSaveTimer) {
    window.clearTimeout(scrapeInputSaveTimer);
    scrapeInputSaveTimer = null;
  }
  if (popupLivePort) {
    try {
      popupLivePort.disconnect();
    } catch (_error) {
    }
    popupLivePort = null;
  }
});

// Silently fetch the bridge token so Nyxify can reach its local runner API
// (:8866). The NyxSuite (bridge) toggle starts/stops the shared bridge agent.
function fetchTokenFromApi() {
  const apiUrl = "http://127.0.0.1:8866";
  fetch(apiUrl + "/token")
    .then((r) => r.json())
    .then((data) => {
      if (data && data.ok && data.token) {
        chrome.runtime.sendMessage({
          type: "NYXIFY_SAVE_CONFIG",
          localToken: data.token,
          localApiUrl: apiUrl,
        }, () => { refreshPopupStatus(undefined, true); });
      }
    })
    .catch(() => {});
}

// ---------------------------------------------------------------- NyxSuite bridge
// The bridge agent is shared with the Nyx extension; both extensions are allowed
// origins of the com.nyxsuite.agent native host, so Nyxify can start it too.
const DASHBOARD_URL = "http://127.0.0.1:8870/";

function focusOrCreateDashboard(url, setUrl) {
  chrome.tabs.query({}, (tabs) => {
    const existing = (tabs || []).find((t) => t.url && t.url.indexOf(DASHBOARD_URL) === 0);
    if (existing) {
      const upd = { active: true };
      if (setUrl) upd.url = url;
      chrome.tabs.update(existing.id, upd);
      if (existing.windowId != null) chrome.windows.update(existing.windowId, { focused: true });
    } else {
      chrome.tabs.create({ url: url });
    }
  });
}
// Nyxify's Open Dashboard deep-links straight to the Nyxify section.
function openWebApp() { focusOrCreateDashboard(DASHBOARD_URL + "#nyxify", true); }

function startBridgeViaNative() {
  return new Promise((resolve) => {
    try {
      chrome.runtime.sendNativeMessage("com.nyxsuite.agent", { type: "start_agent" }, (resp) => {
        if (chrome.runtime.lastError) { resolve({ ok: false, error: chrome.runtime.lastError.message }); return; }
        resolve(resp || { ok: false });
      });
    } catch (e) { resolve({ ok: false, error: String(e) }); }
  });
}

// Lightweight liveness probe for the native host (does NOT start the bridge) —
// lets us tell "host genuinely not registered" apart from a transient failure.
function pingNativeHost() {
  return new Promise((resolve) => {
    try {
      chrome.runtime.sendNativeMessage("com.nyxsuite.agent", { type: "ping" }, (resp) => {
        if (chrome.runtime.lastError) { resolve({ ok: false, error: chrome.runtime.lastError.message }); return; }
        resolve(resp || { ok: false });
      });
    } catch (e) { resolve({ ok: false, error: String(e) }); }
  });
}

// True only when the error clearly means the native host is not registered for
// this browser — NOT a blank error or host-crash, which are transient.
function isHostMissingError(errStr) {
  const err = String(errStr || "").toLowerCase();
  if (!err) return false;
  return err.includes("not found")
      || err.includes("forbidden")
      || err.includes("not registered")
      || err.includes("native messaging host");
}

function checkAgentRunning() {
  return fetch(DASHBOARD_URL, { method: "HEAD", cache: "no-store" }).then(() => true).catch(() => false);
}

async function stopBridge() {
  const token = await new Promise((res) =>
    chrome.storage.sync.get(["nyxifyConfig"], (d) => res(((d && d.nyxifyConfig) || {}).localToken || "")));
  try {
    await fetch(DASHBOARD_URL + "bridge/shutdown", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Nyx-Token": token, "X-Nyxify-Token": token },
      body: JSON.stringify({ token: token }),
    });
  } catch (e) { /* already down */ }
}

const bridgeToggle = document.getElementById("bridgePowerToggle");
const nyxsuiteToggleText = document.getElementById("nyxsuiteToggleText");

function setNyxsuiteIndicator(running, busy) {
  if (nyxsuiteToggleText) {
    nyxsuiteToggleText.textContent = busy ? "NyxSuite …" : (running ? "NyxSuite on" : "NyxSuite off");
  }
  if (busy) return;
  const dot = document.getElementById("runnerDot");
  const text = document.getElementById("runnerConnectionText");
  if (dot) {
    dot.classList.toggle("runner-dot-online", !!running);
    dot.classList.toggle("runner-dot-offline", !running);
  }
  if (text) text.textContent = running ? "NyxSuite connected" : "NyxSuite disconnected";
}

function renderBridgeToggle(running, busy) {
  if (!bridgeToggle) return;
  bridgeToggle.dataset.running = running ? "true" : "false";
  bridgeToggle.disabled = !!busy;
  if (!busy) bridgeToggle.checked = !!running;
  setNyxsuiteIndicator(running, busy);
}

function refreshBridgeToggle() {
  if (!bridgeToggle || bridgeToggle.dataset.busy === "true") return;
  checkAgentRunning().then((running) => {
    if (bridgeToggle.dataset.busy === "true") return;
    renderBridgeToggle(running, false);
    if (running) fetchTokenFromApi();
  });
}

if (bridgeToggle) {
  bridgeToggle.addEventListener("change", async () => {
    const wantOn = bridgeToggle.checked;
    bridgeToggle.dataset.busy = "true";
    bridgeToggle.disabled = true;
    setNyxsuiteIndicator(wantOn, true);
    if (!wantOn) {
      await stopBridge();
      setPrimaryStatus("NyxSuite stopping…", 2500);
      setTimeout(() => { bridgeToggle.dataset.busy = "false"; refreshBridgeToggle(); }, 2500);
    } else {
      setPrimaryStatus("Starting NyxSuite…", 2500);
      // Already up (toggled off then on faster than it shut down)? Reflect it.
      if (await checkAgentRunning()) {
        bridgeToggle.dataset.busy = "false";
        renderBridgeToggle(true, false);
        fetchTokenFromApi();
        return;
      }
      const r = await startBridgeViaNative();
      if (!r.ok) {
        // Only claim "not installed" when the host is genuinely unregistered.
        // The bridge registers the host on first launch and that survives
        // restarts, so a post-run failure is almost always transient (the
        // just-stopped bridge is still releasing its lock). Confirm with a ping.
        let hostMissing = isHostMissingError(r.error);
        if (!hostMissing) {
          const probe = await pingNativeHost();
          hostMissing = !probe.ok && isHostMissingError(probe.error);
        }
        if (hostMissing) {
          setPrimaryStatus("NyxSuite isn't installed for this browser yet. Double-click run_nyx_suite once (or use Setup & Install in the Nyx extension), then try again.", 6000);
          bridgeToggle.dataset.busy = "false";
          renderBridgeToggle(false, false);
          return;
        }
        // Host is registered; the bridge is likely still coming up. Fall through
        // to polling instead of falsely claiming it isn't installed.
      }
      let tries = 0;
      const poll = setInterval(async () => {
        tries += 1;
        const up = await checkAgentRunning();
        if (up) {
          clearInterval(poll);
          bridgeToggle.dataset.busy = "false";
          renderBridgeToggle(true, false);
          fetchTokenFromApi();
        } else if (tries > 25) {
          clearInterval(poll);
          bridgeToggle.dataset.busy = "false";
          renderBridgeToggle(false, false);
          setPrimaryStatus("NyxSuite didn't come online — try Setup & Install in the Nyx extension.", 4500);
        }
      }, 800);
    }
  });
}

const openWebAppButton = document.getElementById("openWebAppButton");
if (openWebAppButton) openWebAppButton.addEventListener("click", openWebApp);

setActivePopupView(window.localStorage.getItem(POPUP_VIEW_STORAGE_KEY) || "runnerView");
applyStoredSettingsSnapshot();
connectLiveStatus();
refreshBridgeToggle();
setInterval(refreshBridgeToggle, 5000);

chrome.storage.sync.get(["nyxifyConfig"], (data) => {
  const config = data && data.nyxifyConfig ? data.nyxifyConfig : {};
  if (!config.localToken) {
    fetchTokenFromApi();
  } else {
    refreshPopupStatus(undefined, true);
  }
});
