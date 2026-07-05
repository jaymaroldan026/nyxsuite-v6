const saveButton = document.getElementById("saveButton");
const feedback = document.getElementById("feedback");
const localApiUrlInput = document.getElementById("localApiUrl");
const localTokenInput = document.getElementById("localToken");
const remoteConfigUrlInput = document.getElementById("remoteConfigUrl");
const enabledInput = document.getElementById("enabled");
const rowLimitInput = document.getElementById("rowLimit");
const pendingThresholdInput = document.getElementById("pendingThreshold");
const maxParallelProfilesInput = document.getElementById("maxParallelProfiles");
const ignoreDoneProfilesInput = document.getElementById("ignoreDoneProfiles");

const launchOnWindowsStartupInput = document.getElementById("launchOnWindowsStartup");
const clearDetectedDataButton = document.getElementById("clearDetectedDataButton");
const pruneCompletedButton = document.getElementById("pruneCompletedButton");
const clearQueueButton = document.getElementById("clearQueueButton");
const clearCacheLogsButton = document.getElementById("clearCacheLogsButton");
const exportConfigButton = document.getElementById("exportConfigButton");
const downloadOnlineConfigButton = document.getElementById("downloadOnlineConfigButton");
const importConfigFile = document.getElementById("importConfigFile");
let settingsLoaded = false;
let settingsSaveTimer = null;

function applyStatusToSettings(status) {
  const config = status.config || {};
  const runnerConfig = (status.runnerStatus && status.runnerStatus.config) || {};
  localApiUrlInput.value = config.localApiUrl || "http://127.0.0.1:8865";
  localTokenInput.value = config.localToken || "";
  remoteConfigUrlInput.value = config.remoteConfigUrl || "";
  enabledInput.checked = config.enabled !== false;
  rowLimitInput.value = config.rowLimit || 100;
  pendingThresholdInput.value = runnerConfig.pending_threshold || 10;
  maxParallelProfilesInput.value = runnerConfig.max_parallel_profiles || 5;
  ignoreDoneProfilesInput.checked = runnerConfig.ignore_done_profiles !== false;

  launchOnWindowsStartupInput.checked = runnerConfig.launch_on_windows_startup === true;
}

function saveSettings(options = {}) {
  if (options.statusMessage) {
    feedback.textContent = options.statusMessage;
  }

  chrome.runtime.sendMessage(
    {
      type: "NYX_SAVE_CONFIG",
      localApiUrl: localApiUrlInput.value,
      localToken: localTokenInput.value,
      remoteConfigUrl: remoteConfigUrlInput.value,
      enabled: enabledInput.checked,
      rowLimit: rowLimitInput.value,
      pendingThreshold: pendingThresholdInput.value,
      maxParallelProfiles: maxParallelProfilesInput.value,
      ignoreDoneProfiles: ignoreDoneProfilesInput.checked,

      launchOnWindowsStartup: launchOnWindowsStartupInput.checked,
    },
    (response) => {
      feedback.textContent = response && response.ok
        ? (options.successMessage || "Nyx settings saved.")
        : ((response && response.error) || "Could not save Nyx settings.");
    }
  );
}

function scheduleSettingsSave() {
  if (!settingsLoaded) {
    return;
  }
  if (settingsSaveTimer) {
    window.clearTimeout(settingsSaveTimer);
  }
  settingsSaveTimer = window.setTimeout(() => {
    settingsSaveTimer = null;
    saveSettings({
      statusMessage: "Applying Nyx setting...",
      successMessage: "Nyx setting applied.",
    });
  }, 250);
}

chrome.runtime.sendMessage({ type: "NYX_GET_STATUS" }, (response) => {
  if (!response || !response.ok) {
    feedback.textContent = (response && response.error) || "Could not load current Nyx settings.";
    return;
  }

  applyStatusToSettings(response.status || {});
  settingsLoaded = true;
});

saveButton.addEventListener("click", () => saveSettings());

[
  localApiUrlInput,
  localTokenInput,
  remoteConfigUrlInput,
  enabledInput,
  rowLimitInput,
  pendingThresholdInput,
  maxParallelProfilesInput,
  ignoreDoneProfilesInput,

  launchOnWindowsStartupInput,
].forEach((input) => {
  input.addEventListener("change", scheduleSettingsSave);
});

clearDetectedDataButton.addEventListener("click", () => {
  feedback.textContent = "Clearing recorded SnapBoard IDs and models...";

  chrome.runtime.sendMessage({ type: "NYX_CLEAR_DETECTED_DATA" }, (response) => {
    feedback.textContent = response && response.ok
      ? (response.result && response.result.message ? response.result.message : "Cleared recorded IDs and models.")
      : ((response && response.error) || "Could not clear recorded IDs and models.");
  });
});

pruneCompletedButton.addEventListener("click", () => {
  feedback.textContent = "Deleting old DONE rows and keeping the newest 150...";

  chrome.runtime.sendMessage({ type: "NYX_PRUNE_COMPLETED_KEEP_150" }, (response) => {
    feedback.textContent = response && response.ok
      ? ((response.payload && response.payload.message) || "Deleted old DONE rows, keeping the newest 150.")
      : ((response && response.error) || "Could not delete old DONE rows.");
  });
});

clearQueueButton.addEventListener("click", () => {
  feedback.textContent = "Clearing Nyx IDs and queue...";

  chrome.runtime.sendMessage({ type: "NYX_CLEAR_ALL" }, (response) => {
    feedback.textContent = response && response.ok
      ? "Cleared Nyx IDs and queue."
      : ((response && response.error) || "Could not clear Nyx IDs and queue.");
  });
});

clearCacheLogsButton.addEventListener("click", () => {
  feedback.textContent = "Clearing Nyx cache and logs...";

  chrome.runtime.sendMessage({ type: "NYX_CLEAR_CACHE_LOGS" }, (response) => {
    feedback.textContent = response && response.ok
      ? (response.result && response.result.message ? response.result.message : "Cleared Nyx cache and logs.")
      : ((response && response.error) || "Could not clear Nyx cache/logs.");
  });
});

exportConfigButton.addEventListener("click", () => {
  feedback.textContent = "Preparing Nyx config export...";

  chrome.runtime.sendMessage({ type: "NYX_EXPORT_CONFIG" }, (response) => {
    if (!response || !response.ok) {
      feedback.textContent = (response && response.error) || "Could not export Nyx config.";
      return;
    }

    const blob = new Blob([JSON.stringify(response.config, null, 2)], { type: "application/json" });
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = "nyx_v2_config.json";
    link.click();
    URL.revokeObjectURL(objectUrl);
    feedback.textContent = "Nyx config exported.";
  });
});

downloadOnlineConfigButton.addEventListener("click", () => {
  const remoteUrl = String(remoteConfigUrlInput.value || "").trim();

  if (!remoteUrl) {
    feedback.textContent = "Online config URL is required.";
    return;
  }

  window.open(remoteUrl, "_blank", "noopener,noreferrer");
  feedback.textContent = "Opened online config link. Download it, then use Local Update.";
});

importConfigFile.addEventListener("change", () => {
  const file = importConfigFile.files && importConfigFile.files[0];
  if (!file) {
    return;
  }

  feedback.textContent = "Importing Nyx config...";

  const reader = new FileReader();
  reader.onload = () => {
    try {
      const parsed = JSON.parse(String(reader.result || "{}"));
      chrome.runtime.sendMessage({ type: "NYX_IMPORT_CONFIG", config: parsed }, (response) => {
        if (!response || !response.ok) {
          feedback.textContent = (response && response.error) || "Could not import Nyx config.";
          return;
        }

        applyStatusToSettings(response.status || {});
        feedback.textContent = "Nyx config imported.";
      });
    } catch (error) {
      feedback.textContent = "Invalid Nyx config file.";
    } finally {
      importConfigFile.value = "";
    }
  };
  reader.readAsText(file);
});
