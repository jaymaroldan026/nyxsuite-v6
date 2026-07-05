const LIVE_PORT_NAME = "nyxify-popup-live";

let scrapeLivePort = null;
let scrapeLiveReconnectTimer = null;
let renderedScrapeSignature = "";
let renderedRecordsSignature = "";

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function normalizeStatus(value) {
  return String(value || "").trim().toLowerCase();
}

function getStatusMeta(status) {
  const normalizedStatus = normalizeStatus(status);
  if (normalizedStatus === "has_bitmoji") {
    return { label: "Has Bitmoji", tone: "has-bitmoji" };
  }
  if (normalizedStatus === "no_bitmoji") {
    return { label: "No Bitmoji", tone: "no-bitmoji" };
  }
  if (normalizedStatus === "not_found") {
    return { label: "No Account", tone: "not-found" };
  }
  return { label: "Unknown", tone: "unknown" };
}

function formatCheckedAt(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}

function getResultsByStatuses(results, statuses) {
  const allowed = new Set((statuses || []).map((status) => normalizeStatus(status)));
  return (results || []).filter((entry) => allowed.has(normalizeStatus(entry && entry.status)));
}

function buildUsernameList(entries) {
  return (entries || []).map((entry) => String(entry && entry.username || "").trim()).filter(Boolean).join("\n");
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

function renderRecordsTable(results) {
  const container = document.getElementById("scrapeRecordsTable");
  if (!container) {
    return;
  }

  const nextSignature = JSON.stringify((results || []).map((entry) => [
    String(entry && entry.username || ""),
    String(entry && entry.status || ""),
    String(entry && entry.checked_at || ""),
    String(entry && entry.evidence || ""),
    String(entry && entry.profile_url || ""),
  ]));
  if (nextSignature === renderedRecordsSignature) {
    return;
  }
  renderedRecordsSignature = nextSignature;

  if (!results || !results.length) {
    container.innerHTML = '<div class="queue-table-empty">No scrape records yet.</div>';
    return;
  }

  const header = `
    <div class="scrape-records-row scrape-records-header">
      <div>Username</div>
      <div>Status</div>
      <div>Checked At</div>
      <div>Evidence</div>
      <div>Link</div>
    </div>
  `;

  const rows = results.map((entry) => {
    const username = String(entry && entry.username || "").trim();
    const statusMeta = getStatusMeta(entry && entry.status);
    const checkedAt = formatCheckedAt(entry && entry.checked_at);
    const evidence = String(entry && entry.evidence || "").trim() || "-";
    const profileUrl = String(entry && entry.profile_url || "").trim();
    const linkCell = profileUrl
      ? `<a href="${escapeHtml(profileUrl)}" target="_blank" rel="noreferrer">Open</a>`
      : "-";

    return `
      <div class="scrape-records-row">
        <div>${escapeHtml(username || "-")}</div>
        <div><span class="scrape-status-pill scrape-status-pill-${escapeHtml(statusMeta.tone)}">${escapeHtml(statusMeta.label)}</span></div>
        <div>${escapeHtml(checkedAt)}</div>
        <div>${escapeHtml(evidence)}</div>
        <div>${linkCell}</div>
      </div>
    `;
  }).join("");

  container.innerHTML = header + rows;
}

function renderScrapeStatus(status) {
  const safeStatus = status || {};
  const config = safeStatus.config || {};
  const results = Array.isArray(safeStatus.scrapeResults) ? safeStatus.scrapeResults.slice() : [];
  const eventLog = Array.isArray(safeStatus.eventLog) ? safeStatus.eventLog : [];
  const runnerState = safeStatus.runnerState || {};
  const inputText = String(safeStatus.inputText || "");
  const inputCount = Number(safeStatus.inputCount || 0);
  const checkedCount = results.length;
  const withAccountEntries = getResultsByStatuses(results, ["no_bitmoji", "has_bitmoji"]);
  const noAccountEntries = getResultsByStatuses(results, ["not_found"]);
  const unknownEntries = getResultsByStatuses(results, ["unknown"]);
  const runnerStatus = String(runnerState.status || "idle");
  const currentUsername = String(runnerState.current_username || "").trim() || "-";
  const nextSignature = JSON.stringify({
    config: {
      maxParallelTabs: config.maxParallelTabs || 4,
      profileTimeoutMs: config.profileTimeoutMs || 12000,
    },
    inputText,
    inputCount,
    runnerStatus,
    currentUsername,
    activeCount: Number(runnerState.active_count || 0),
    completed: Number(runnerState.completed || 0),
    total: Number(runnerState.total || inputCount || 0),
    hasBitmoji: Number(runnerState.has_bitmoji || 0),
    noBitmoji: Number(runnerState.no_bitmoji || 0),
    noAccount: Number(runnerState.not_found || 0),
    unknown: Number(runnerState.unknown || 0),
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
  if (nextSignature === renderedScrapeSignature) {
    return;
  }
  renderedScrapeSignature = nextSignature;

  setElementText("scrapeStatusLine", runnerStatus === "running"
    ? `Username scrape is running. Checked ${Number(runnerState.completed || 0)} of ${Number(runnerState.total || inputCount || 0)}.`
    : runnerStatus === "paused"
      ? `Username scrape paused. Checked ${Number(runnerState.completed || 0)} of ${Number(runnerState.total || inputCount || 0)}.`
      : checkedCount
        ? `Checked ${checkedCount} username(s).`
        : "Paste usernames and click Check.");

  // Pause shows only while running; Resume only while paused.
  const pauseBtn = document.getElementById("scrapePauseButton");
  const resumeBtn = document.getElementById("scrapeResumeButton");
  if (pauseBtn) { pauseBtn.style.display = runnerStatus === "running" ? "" : "none"; }
  if (resumeBtn) { resumeBtn.style.display = runnerStatus === "paused" ? "" : "none"; }

  setElementText("scrapeRunnerSummary", [
    `Session state: ${runnerStatus}`,
    `Current: ${currentUsername}`,
    `Completed: ${Number(runnerState.completed || 0)}/${Number(runnerState.total || 0)}`,
    `Has Bitmoji: ${Number(runnerState.has_bitmoji || 0)}`,
    `No Bitmoji: ${Number(runnerState.no_bitmoji || 0)}`,
    `No Account: ${Number(runnerState.not_found || 0)}`,
    `Unknown: ${Number(runnerState.unknown || 0)}`,
  ].join("\n"));

  setInputValue("scrapeParallelTabsInput", config.maxParallelTabs || 4);
  setInputValue("scrapeTimeoutMsInput", config.profileTimeoutMs || 12000);
  setTextAreaValue("scrapeInputText", inputText);

  setElementText("scrapeInputCount", String(inputCount));
  setElementText("scrapeCheckedCount", String(checkedCount));
  setElementText("scrapeWithAccountCount", String(withAccountEntries.length));
  setElementText("scrapeNoAccountCount", String(noAccountEntries.length));
  setElementText("scrapeUnknownCount", String(unknownEntries.length));

  setElementText("withAccountBadge", String(withAccountEntries.length));
  setElementText("noAccountBadge", String(noAccountEntries.length));
  setElementText("unknownBadge", String(unknownEntries.length));

  setTextAreaValue("withAccountResults", buildUsernameList(withAccountEntries));
  setTextAreaValue("noAccountResults", buildUsernameList(noAccountEntries));
  setTextAreaValue("unknownResults", buildUsernameList(unknownEntries));

  setElementText("scrapeEventLog", eventLog.length
    ? eventLog.map((entry) => {
        const at = entry && entry.at ? new Date(entry.at).toLocaleString() : "-";
        return `[${at}] ${String(entry && entry.message || "").trim()}`;
      }).join("\n")
    : "No scrape events yet.");

  results.sort((left, right) => {
    const leftIndex = Number.isFinite(Number(left && left.input_index)) ? Number(left.input_index) : Number.MAX_SAFE_INTEGER;
    const rightIndex = Number.isFinite(Number(right && right.input_index)) ? Number(right.input_index) : Number.MAX_SAFE_INTEGER;
    if (leftIndex !== rightIndex) {
      return leftIndex - rightIndex;
    }
    return String(left && left.username || "").localeCompare(String(right && right.username || ""));
  });
  renderRecordsTable(results);
}

function refreshScrapeStatus(statusMessage) {
  if (statusMessage) {
    setElementText("scrapeStatusLine", statusMessage);
  }

  chrome.runtime.sendMessage({ type: "NYXIFY_SCRAPE_GET_STATUS" }, (response) => {
    if (!response || !response.ok) {
      setElementText("scrapeStatusLine", (response && response.error) || "Could not load scrape status.");
      return;
    }
    renderScrapeStatus(response.status || {});
  });
}

function getConfigPayload() {
  return {
    maxParallelTabs: document.getElementById("scrapeParallelTabsInput").value,
    profileTimeoutMs: document.getElementById("scrapeTimeoutMsInput").value,
  };
}

function saveScrapeSettings() {
  chrome.runtime.sendMessage({ type: "NYXIFY_SCRAPE_SAVE_CONFIG", config: getConfigPayload() }, (response) => {
    setElementText(
      "scrapeStatusLine",
      response && response.ok ? "Username scrape settings saved." : ((response && response.error) || "Could not save username scrape settings.")
    );
    if (response && response.ok) {
      refreshScrapeStatus();
    }
  });
}

function startScrapeRun() {
  setElementText("scrapeStatusLine", "Starting username scrape...");
  chrome.runtime.sendMessage({
    type: "NYXIFY_SCRAPE_START",
    inputText: document.getElementById("scrapeInputText").value,
    config: getConfigPayload(),
  }, (response) => {
    if (!response || !response.ok) {
      setElementText("scrapeStatusLine", (response && response.error) || "Could not start username scrape.");
      return;
    }
    refreshScrapeStatus("Username scrape started.");
  });
}

function pauseScrapeRun() {
  setElementText("scrapeStatusLine", "Pausing username scrape...");
  chrome.runtime.sendMessage({ type: "NYXIFY_SCRAPE_PAUSE" }, (response) => {
    if (!response || !response.ok) {
      setElementText("scrapeStatusLine", (response && response.error) || "Could not pause username scrape.");
      return;
    }
    refreshScrapeStatus("Username scrape paused.");
  });
}

function resumeScrapeRun() {
  setElementText("scrapeStatusLine", "Resuming username scrape...");
  chrome.runtime.sendMessage({ type: "NYXIFY_SCRAPE_RESUME" }, (response) => {
    if (!response || !response.ok) {
      setElementText("scrapeStatusLine", (response && response.error) || "Could not resume username scrape.");
      return;
    }
    refreshScrapeStatus("Username scrape resumed.");
  });
}

function stopScrapeRun() {
  setElementText("scrapeStatusLine", "Stopping username scrape...");
  chrome.runtime.sendMessage({ type: "NYXIFY_SCRAPE_STOP" }, (response) => {
    if (!response || !response.ok) {
      setElementText("scrapeStatusLine", (response && response.error) || "Could not stop username scrape.");
      return;
    }
    refreshScrapeStatus("Username scrape stopped.");
  });
}

function clearScrapeData() {
  setElementText("scrapeStatusLine", "Clearing username scrape data...");
  chrome.runtime.sendMessage({ type: "NYXIFY_SCRAPE_CLEAR" }, (response) => {
    setElementText(
      "scrapeStatusLine",
      response && response.ok ? "Username scrape data cleared." : ((response && response.error) || "Could not clear username scrape data.")
    );
    if (response && response.ok) {
      refreshScrapeStatus();
    }
  });
}

function saveInputText() {
  chrome.runtime.sendMessage({
    type: "NYXIFY_SCRAPE_SAVE_INPUT",
    inputText: document.getElementById("scrapeInputText").value,
  }, () => {});
}

async function copyGroupedResults(statuses, emptyMessage, successMessage) {
  chrome.runtime.sendMessage({ type: "NYXIFY_SCRAPE_GET_STATUS" }, async (response) => {
    if (!response || !response.ok) {
      setElementText("scrapeStatusLine", (response && response.error) || "Could not load scrape status.");
      return;
    }

    const results = Array.isArray(response.status && response.status.scrapeResults) ? response.status.scrapeResults : [];
    const output = buildUsernameList(getResultsByStatuses(results, statuses));
    if (!output) {
      setElementText("scrapeStatusLine", emptyMessage);
      return;
    }

    try {
      await navigator.clipboard.writeText(output);
      setElementText("scrapeStatusLine", successMessage);
    } catch (_error) {
      setElementText("scrapeStatusLine", "Could not copy usernames.");
    }
  });
}

function scheduleLiveReconnect() {
  if (scrapeLiveReconnectTimer) {
    window.clearTimeout(scrapeLiveReconnectTimer);
  }
  scrapeLiveReconnectTimer = window.setTimeout(() => {
    scrapeLiveReconnectTimer = null;
    connectLiveStatus();
  }, 700);
}

function connectLiveStatus() {
  if (scrapeLivePort) {
    return;
  }

  try {
    scrapeLivePort = chrome.runtime.connect({ name: LIVE_PORT_NAME });
  } catch (_error) {
    scheduleLiveReconnect();
    return;
  }

  scrapeLivePort.onMessage.addListener((message) => {
    if (!message) {
      return;
    }
    if (message.type === "status") {
      renderScrapeStatus((message.status && message.status.scrapeStatus) || {});
      return;
    }
    if (message.type === "status-error") {
      setElementText("scrapeStatusLine", message.error || "Could not load scrape status.");
    }
  });

  scrapeLivePort.onDisconnect.addListener(() => {
    scrapeLivePort = null;
    if (!document.hidden) {
      scheduleLiveReconnect();
    }
  });
}

document.getElementById("scrapeRefreshButton").addEventListener("click", () => refreshScrapeStatus("Refreshing scrape status..."));
document.getElementById("scrapeStartButton").addEventListener("click", startScrapeRun);
document.getElementById("scrapePauseButton").addEventListener("click", pauseScrapeRun);
document.getElementById("scrapeResumeButton").addEventListener("click", resumeScrapeRun);
document.getElementById("scrapeStopButton").addEventListener("click", stopScrapeRun);
document.getElementById("scrapeClearButton").addEventListener("click", clearScrapeData);
document.getElementById("scrapeSaveButton").addEventListener("click", saveScrapeSettings);
document.getElementById("scrapeOpenOptionsButton").addEventListener("click", () => {
  chrome.runtime.openOptionsPage();
});
document.getElementById("scrapeInputText").addEventListener("input", saveInputText);
document.getElementById("copyWithAccountButton").addEventListener("click", () => {
  copyGroupedResults(["no_bitmoji", "has_bitmoji"], "No usernames with account yet.", "Copied usernames with account.");
});
document.getElementById("copyNoAccountButton").addEventListener("click", () => {
  copyGroupedResults(["not_found"], "No no-account usernames yet.", "Copied usernames with no account.");
});

document.addEventListener("visibilitychange", () => {
  if (!document.hidden) {
    connectLiveStatus();
    refreshScrapeStatus("Refreshing scrape status...");
    return;
  }
  if (scrapeLivePort) {
    try {
      scrapeLivePort.disconnect();
    } catch (_error) {
    }
    scrapeLivePort = null;
  }
});

window.addEventListener("beforeunload", () => {
  if (scrapeLiveReconnectTimer) {
    window.clearTimeout(scrapeLiveReconnectTimer);
    scrapeLiveReconnectTimer = null;
  }
  if (scrapeLivePort) {
    try {
      scrapeLivePort.disconnect();
    } catch (_error) {
    }
    scrapeLivePort = null;
  }
});

connectLiveStatus();
refreshScrapeStatus();
