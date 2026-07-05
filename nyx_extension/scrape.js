function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function getStatusMeta(status, evidence) {
  const normalizedStatus = String(status || "").trim().toLowerCase();
  const normalizedEvidence = String(evidence || "").trim().toLowerCase();

  if (normalizedStatus === "has_bitmoji") {
    return { emoji: "✅", label: "Has Bitmoji" };
  }
  if (normalizedStatus === "no_bitmoji") {
    return { emoji: "❌", label: "No Bitmoji" };
  }
  if (normalizedStatus === "not_found") {
    return { emoji: "🔍", label: "Not Found" };
  }
  if (normalizedEvidence === "timeout") {
    return { emoji: "⏱️", label: "Timeout" };
  }
  return { emoji: "⚠️", label: "Unknown" };
}

function buildEvidenceTitle(evidence, entries) {
  const normalizedEvidence = String(evidence || "").trim() || "unknown";
  const first = entries && entries.length ? entries[0] : {};
  const statusMeta = getStatusMeta(first && first.status, normalizedEvidence);
  const evidenceLabel = normalizedEvidence.replace(/-/g, " ");
  return `${statusMeta.emoji} ${statusMeta.label} (${evidenceLabel})`;
}

function formatCheckedAt(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toISOString();
}

function renderGroupedResults(results) {
  const container = document.getElementById("scrapeResultsGroups");
  if (!container) {
    return;
  }

  if (!results.length) {
    container.innerHTML = '<div class="queue-table-empty">No scrape results yet.</div>';
    return;
  }

  const groups = new Map();
  results.forEach((entry) => {
    const evidence = String(entry && entry.evidence || "unknown-layout").trim() || "unknown-layout";
    if (!groups.has(evidence)) {
      groups.set(evidence, []);
    }
    groups.get(evidence).push(entry);
  });

  const groupedHtml = Array.from(groups.entries())
    .sort((a, b) => b[1].length - a[1].length)
    .map(([evidence, entries]) => {
      const title = buildEvidenceTitle(evidence, entries);
      const header = `
        <div class="scrape-group-header">
          <div class="scrape-group-title">${escapeHtml(title)}</div>
          <span class="scrape-group-count">${entries.length}</span>
        </div>
      `;

      const tableHeader = `
        <div class="scrape-results-row scrape-results-header">
          <div>Username</div>
          <div>Status</div>
          <div>Checked At</div>
          <div>Evidence</div>
          <div>Link</div>
        </div>
      `;

      const rows = entries
        .slice()
        .sort((a, b) => String(b && b.checked_at || "").localeCompare(String(a && a.checked_at || "")))
        .map((entry) => {
          const statusMeta = getStatusMeta(entry && entry.status, entry && entry.evidence);
          const username = escapeHtml(entry && entry.username || "-");
          const statusText = escapeHtml(String(entry && entry.status || "unknown").replace(/_/g, " "));
          const checkedAt = escapeHtml(formatCheckedAt(entry && entry.checked_at));
          const evidenceText = escapeHtml(entry && entry.evidence || "-");
          const profileUrl = String(entry && entry.profile_url || "").trim();
          const linkCell = profileUrl
            ? `<a href="${escapeHtml(profileUrl)}" target="_blank" rel="noreferrer">Open</a>`
            : "-";

          return `
            <div class="scrape-results-row">
              <div>${username}</div>
              <div>${statusMeta.emoji} ${statusText}</div>
              <div>${checkedAt}</div>
              <div>${evidenceText}</div>
              <div>${linkCell}</div>
            </div>
          `;
        }).join("");

      return `
        <section class="scrape-results-group">
          ${header}
          <div class="scrape-results-table">
            ${tableHeader}
            ${rows}
          </div>
        </section>
      `;
    }).join("");

  container.innerHTML = groupedHtml;
}

function renderScrapeStatus(status) {
  const config = status && status.config ? status.config : {};
  const rows = status && Array.isArray(status.snapboardRows) ? status.snapboardRows : [];
  const results = status && Array.isArray(status.scrapeResults) ? status.scrapeResults : [];
  const runnerState = status && status.runnerState ? status.runnerState : {};
  const runnerStatus = String(runnerState.status || "idle");
  const isActiveSession = Number(runnerState.total || 0) > 0 || Number(runnerState.completed || 0) > 0;

  document.getElementById("scrapeStatusLine").textContent = isActiveSession
    ? `Session: ${runnerStatus} | Collected: ${rows.length} | Checked: ${results.length}`
    : "Session-only checker. Starts only when you press Scrape in popup.";
  document.getElementById("scrapeRunnerSummary").textContent = [
    `Session state: ${isActiveSession ? runnerStatus : "waiting"}`,
    `Current: ${String(runnerState.current_username || "-")}`,
    `Completed: ${Number(runnerState.completed || 0)}/${Number(runnerState.total || 0)}`,
    `Has Bitmoji: ${Number(runnerState.has_bitmoji || 0)}`,
    `No Bitmoji: ${Number(runnerState.no_bitmoji || 0)}`,
    `Not Found: ${Number(runnerState.not_found || 0)}`,
    `Unknown: ${Number(runnerState.unknown || 0)}`,
  ].join("\n");

  document.getElementById("scrapeEnabledInput").checked = config.enabled !== false;
  document.getElementById("scrapeMaxProfilesInput").value = config.maxProfilesPerRun || 25;
  document.getElementById("scrapeParallelTabsInput").value = config.maxParallelTabs || 3;
  document.getElementById("scrapeTimeoutMsInput").value = config.profileTimeoutMs || 8000;
  document.getElementById("scrapeNyxLocalApiUrlInput").value = config.nyxLocalApiUrl || "";
  document.getElementById("scrapeNyxSharedSecretInput").value = config.nyxSharedSecret || "";
  document.getElementById("scrapeDailyStartInput").value = config.dailyStartAdspowerId || "";
  renderGroupedResults(results);
}

function refreshScrapeStatus(statusMessage) {
  if (statusMessage) {
    document.getElementById("scrapeStatusLine").textContent = statusMessage;
  }

  chrome.runtime.sendMessage({ type: "NYX_SCRAPE_GET_STATUS" }, (response) => {
    if (!response || !response.ok) {
      document.getElementById("scrapeStatusLine").textContent = (response && response.error) || "Could not load scrape status.";
      return;
    }
    renderScrapeStatus(response.status || {});
  });
}

function saveScrapeSettings() {
  const config = {
    enabled: document.getElementById("scrapeEnabledInput").checked,
    maxProfilesPerRun: document.getElementById("scrapeMaxProfilesInput").value,
    maxParallelTabs: document.getElementById("scrapeParallelTabsInput").value,
    profileTimeoutMs: document.getElementById("scrapeTimeoutMsInput").value,
    nyxLocalApiUrl: document.getElementById("scrapeNyxLocalApiUrlInput").value,
    nyxSharedSecret: document.getElementById("scrapeNyxSharedSecretInput").value,
    dailyStartAdspowerId: document.getElementById("scrapeDailyStartInput").value,
  };

  chrome.runtime.sendMessage({ type: "NYX_SCRAPE_SAVE_CONFIG", config }, (response) => {
    document.getElementById("scrapeStatusLine").textContent =
      response && response.ok ? "Scrape settings saved." : ((response && response.error) || "Could not save scrape settings.");
    if (response && response.ok) {
      refreshScrapeStatus();
    }
  });
}

document.getElementById("scrapeRefreshButton").addEventListener("click", () => refreshScrapeStatus("Refreshing scrape status..."));
document.getElementById("scrapeStopButton").addEventListener("click", () => {
  document.getElementById("scrapeStatusLine").textContent = "Stopping scrape session...";
  chrome.runtime.sendMessage({ type: "NYX_SCRAPE_RUNNER_ACTION", action: "stop" }, (response) => {
    if (!response || !response.ok) {
      document.getElementById("scrapeStatusLine").textContent = (response && response.error) || "Could not stop scrape session.";
      return;
    }
    refreshScrapeStatus("Scrape session stopped.");
  });
});
document.getElementById("scrapeSaveButton").addEventListener("click", saveScrapeSettings);
document.getElementById("scrapeClearButton").addEventListener("click", () => {
  document.getElementById("scrapeStatusLine").textContent = "Clearing scrape data...";
  chrome.runtime.sendMessage({ type: "NYX_SCRAPE_CLEAR_ALL" }, (response) => {
    document.getElementById("scrapeStatusLine").textContent =
      response && response.ok ? "Scrape data cleared." : ((response && response.error) || "Could not clear scrape data.");
    if (response && response.ok) {
      refreshScrapeStatus();
    }
  });
});
document.getElementById("scrapeOpenOptionsButton").addEventListener("click", () => {
  chrome.runtime.openOptionsPage();
});

window.setInterval(() => refreshScrapeStatus(), 3000);
refreshScrapeStatus();
