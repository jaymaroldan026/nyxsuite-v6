(function () {
  var debounceTimer = null;
  var CONFIG_KEY = "nyxifyConfig";
  var otpPollTimer = null;
  var otpPollInFlight = false;
  var proxyRotatePollTimer = null;
  var usernameUpdatePollTimer = null;
  var usernameUpdatePollInFlight = false;
  var adspowerUpdatePollTimer = null;
  var adspowerUpdatePollInFlight = false;
  var adspowerNameUpdatePollTimer = null;
  var adspowerNameUpdatePollInFlight = false;
  var statusUpdatePollTimer = null;
  var statusUpdatePollInFlight = false;
  var configCache = null;
  var configCacheAt = 0;
  var ROW_SCAN_DEBOUNCE_MS = 800;
  var OTP_POLL_INTERVAL_MS = 900;
  var PROXY_ROTATE_POLL_INTERVAL_MS = 1500;
  var USERNAME_UPDATE_POLL_INTERVAL_MS = 1200;
  var OTP_FETCH_TIMEOUT_MS = 30000;
  var EMAIL_FETCH_TIMEOUT_MS = 45000;
  var OTP_CLICK_RETRY_INTERVAL_MS = 2500;
  var PROXY_ROTATE_WAIT_MS = 22000;
  var PROXY_ROTATE_CLICK_ATTEMPTS = 4;
  var bridgePort = null;
  var autoFillPollTimer = null;
  var AUTO_FILL_POLL_MS = 5000;
  var providerLockTimer = null;
  var PROVIDER_LOCK_POLL_MS = 1500;

  function toArray(nodeList) {
    return Array.prototype.slice.call(nodeList || []);
  }

  function normalizeText(value) {
    return String(value || "").trim();
  }

  function normalizeComparableEmail(value) {
    return normalizeText(value).toLowerCase();
  }

  function extractEmailFromText(value) {
    var match = normalizeText(value).match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i);
    return match ? match[0] : "";
  }

  function extractPhoneFromText(value) {
    var text = stripLeadingNonAlphanumeric(normalizeText(value));
    var match = text.match(/\+?\d[\d\s().-]{7,}\d/);
    return match ? normalizeText(match[0]).replace(/[^\d+]/g, "") : "";
  }

  function normalizeHeaderKey(value) {
    return normalizeText(value).toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  }

  function getRowCells(row) {
    return toArray(row ? row.children : []).filter(function (cell) {
      return cell && (cell.tagName === "TD" || cell.tagName === "TH");
    });
  }

  function stripLeadingNonAlphanumeric(value) {
    return String(value || "").replace(/^[^a-zA-Z0-9]+/, "").trim();
  }

  function readCellText(cell) {
    var inputLike;
    var selectedOption;
    var infoSpan;
    var credSpan;

    if (!cell) {
      return "";
    }

    inputLike = cell.querySelector("input, textarea, select");
    if (inputLike) {
      if (inputLike.tagName === "SELECT") {
        selectedOption = inputLike.options[inputLike.selectedIndex];
        return normalizeText((selectedOption && selectedOption.textContent) || inputLike.value || "");
      }
      return normalizeText(inputLike.value || "");
    }

    // Email badge: <span class="cred-email ...">📧 email@gmail.com</span>
    credSpan = cell.querySelector(".cred-email, [class*='email-badge']");
    if (credSpan) {
      return stripLeadingNonAlphanumeric(credSpan.textContent || "");
    }

    // Info cells (proxy, email): <span class="info-text">value</span>
    // Use this instead of full cell text to avoid picking up button labels (↻, 🔄 Check Code)
    infoSpan = cell.querySelector(".info-text");
    if (infoSpan) {
      return stripLeadingNonAlphanumeric(infoSpan.textContent || "");
    }

    return normalizeText(cell.textContent || "");
  }

  function getTableHeaderMap(root) {
    var table = root ? root.closest("table") : null;
    var headerCells = toArray((table && table.querySelectorAll("thead th")) || document.querySelectorAll("thead th, table th"));
    var headerMap = {};

    headerCells.forEach(function (cell, index) {
      var key = normalizeHeaderKey(cell.textContent || "");
      if (key && headerMap[key] === undefined) {
        headerMap[key] = index;
      }
    });

    return headerMap;
  }

  function findHeaderIndex(headerMap, aliases) {
    var i;
    var alias;
    for (i = 0; i < aliases.length; i += 1) {
      alias = normalizeHeaderKey(aliases[i]);
      if (Object.prototype.hasOwnProperty.call(headerMap, alias)) {
        return headerMap[alias];
      }
    }
    return -1;
  }

  function readValueFromAliases(row, headerMap, aliases) {
    var index = findHeaderIndex(headerMap, aliases);
    var cells = getRowCells(row);
    if (index >= 0 && cells[index]) {
      return readCellText(cells[index]);
    }
    return "";
  }

  function readEmailFromRowId(rowId) {
    var row = document.querySelector('tr[data-id="' + rowId + '"]');
    var headerMap;
    var email;
    if (!row) {
      return "";
    }
    headerMap = getTableHeaderMap(row);
    email = extractEmailFromText(readValueFromAliases(row, headerMap, ["email", "gmail", "google", "mail", "google mail"]));
    if (email) {
      return email;
    }
    return extractEmailFromText(row.innerText || row.textContent || "");
  }

  function readPhoneFromRowId(rowId) {
    var row = document.querySelector('tr[data-id="' + rowId + '"]');
    var headerMap;
    var phone;
    if (!row) {
      return "";
    }
    headerMap = getTableHeaderMap(row);
    phone = extractPhoneFromText(readValueFromAliases(row, headerMap, ["phone", "phone number", "sms", "mobile", "number"]));
    if (phone) {
      return phone;
    }
    return "";
  }

  function rowMatchesExpectedEmail(rowId, expectedEmail) {
    var expected = normalizeComparableEmail(expectedEmail);
    var row;
    var actual;

    if (!expected) {
      return true;
    }

    row = document.querySelector('tr[data-id="' + rowId + '"]');
    if (!row) {
      return false;
    }

    actual = normalizeComparableEmail(readEmailFromRowId(rowId));
    if (actual && actual === expected) {
      return true;
    }

    return normalizeComparableEmail(row.innerText || row.textContent || "").indexOf(expected) >= 0;
  }

  function getRowRoot() {
    return document.querySelector("#tableBody")
      || document.querySelector("tbody")
      || document.querySelector("[data-table-body]")
      || document.body;
  }

  function getCandidateRows(root) {
    return toArray(root.querySelectorAll("tr[data-id], tr, [role='row'], [class*='table-row' i], [class*='row' i]")).filter(function (row) {
      return getRowCells(row).length >= 2 || !!row.querySelector("input, select, textarea");
    });
  }

  function getStableRowKey(row, ipAddress, model) {
    var rowId = normalizeText(
      (row && row.getAttribute && row.getAttribute("data-id"))
      || (row && row.dataset && row.dataset.id)
      || (row && row.id)
    );

    if (rowId) {
      return "snapboard:" + rowId.toLowerCase();
    }

    return ("snapboard:" + normalizeText(ipAddress) + "|" + normalizeText(model)).toLowerCase();
  }

  function extractRows(rowLimit) {
    var root = getRowRoot();
    var headerMap = getTableHeaderMap(root);
    var rows = getCandidateRows(root)
      .sort(function (a, b) {
        return a.getBoundingClientRect().top - b.getBoundingClientRect().top;
      })
      .filter(function (row) {
        return row && row.matches && row.matches("tr[data-id]");
      });
    var limit = Math.max(1, parseInt(rowLimit, 10) || 20);

    if (!rows.length) {
      return [];
    }

    return rows.slice(0, limit).map(function (row) {
      var model = readValueFromAliases(row, headerMap, ["model", "face model"]);
      var ipAddress = readValueFromAliases(row, headerMap, ["ip", "ip address", "proxy", "proxy ip", "proxy address"]);
      var proxyAddress = readValueFromAliases(row, headerMap, ["proxy", "proxy address", "ip", "ip address"]) || ipAddress;
      var adspowerId = readValueFromAliases(row, headerMap, ["adspower", "adspower id", "profile id"]);
      var username = readValueFromAliases(row, headerMap, ["username", "snap username", "snapchat username", "user", "snap user"]);
      var email = extractEmailFromText(readValueFromAliases(row, headerMap, ["email", "gmail", "google", "mail", "google mail"]));
      var password = readValueFromAliases(row, headerMap, ["password", "pass", "snap password", "snapchat password", "account password"]);

      if (!model || !ipAddress || adspowerId) {
        return null;
      }

      return {
        row_key: getStableRowKey(row, ipAddress, model),
        model: model,
        ip_address: ipAddress,
        proxy_address: proxyAddress,
        username: username,
        email: email,
        password: password,
        adspower_id: adspowerId,
      };
    }).filter(Boolean);
  }

  function getRowLimit(callback) {
    chrome.storage.sync.get(CONFIG_KEY, function (result) {
      var config = result && result[CONFIG_KEY] ? result[CONFIG_KEY] : {};
      var parsed = parseInt(config.rowLimit, 10);
      callback(Number.isFinite(parsed) && parsed > 0 ? parsed : 20);
    });
  }

  function sendRows() {
    getRowLimit(function (rowLimit) {
      var rows = extractRows(rowLimit);
      if (!rows.length) {
        return;
      }
      chrome.runtime.sendMessage({
        type: "NYXIFY_DETECTED_ROWS",
        rows: rows,
      });
    });
  }

  function queueScan() {
    window.clearTimeout(debounceTimer);
    debounceTimer = window.setTimeout(sendRows, ROW_SCAN_DEBOUNCE_MS);
  }

  function getStoredConfig() {
    return new Promise(function (resolve) {
      var now = Date.now();
      if (configCache && (now - configCacheAt) < 5000) {
        resolve(configCache);
        return;
      }
      chrome.storage.sync.get(CONFIG_KEY, function (result) {
        configCache = result && result[CONFIG_KEY] ? result[CONFIG_KEY] : {};
        configCacheAt = Date.now();
        resolve(configCache);
      });
    });
  }

  function getLocalApiConfig(config) {
    return {
      localApiUrl: String((config && config.localApiUrl) || "http://127.0.0.1:8866").trim(),
      localToken: String((config && config.localToken) || "").trim(),
    };
  }

  function extractRowId(rowKey) {
    var normalized = normalizeText(rowKey);
    if (normalized.toLowerCase().indexOf("snapboard:") === 0) {
      return normalizeText(normalized.slice("snapboard:".length));
    }
    return normalized;
  }

  function connectBridgePort() {
    try {
      bridgePort = chrome.runtime.connect({ name: "nyxify-snapboard-bridge" });
      bridgePort.onDisconnect.addListener(function () {
        bridgePort = null;
        window.setTimeout(connectBridgePort, 1500);
      });
    } catch (_error) {
      bridgePort = null;
      window.setTimeout(connectBridgePort, 1500);
    }
  }

  function buttonMatchesRotateIntent(button) {
    var text = normalizeText(button.innerText || button.textContent || "").toLowerCase();
    var title = normalizeText(button.getAttribute("title") || "").toLowerCase();
    var label = normalizeText(button.getAttribute("aria-label") || "").toLowerCase();
    var dataAction = normalizeText(button.getAttribute("data-action") || "").toLowerCase();
    var className = normalizeText(button.className || "").toLowerCase();
    var onclickText = normalizeText(button.getAttribute("onclick") || "").toLowerCase();
    var hint = [text, title, label, dataAction, className, onclickText].join(" ");
    return hint.indexOf("rotateproxy") >= 0
      || hint.indexOf("rotate proxy") >= 0
      || hint.indexOf("new proxy") >= 0
      || hint.indexOf("refresh proxy") >= 0
      || (hint.indexOf("proxy") >= 0 && (hint.indexOf("refresh") >= 0 || hint.indexOf("reload") >= 0 || hint.indexOf("renew") >= 0 || hint.indexOf("rotate") >= 0));
  }

  function clickElement(button) {
    if (!button) {
      return false;
    }
    try {
      if (typeof button.click === "function") {
        button.click();
        return true;
      }
    } catch (_error) {}
    try {
      button.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
      return true;
    } catch (_error2) {}
    return false;
  }

  function isG5ProviderActive(button) {
    if (!button) {
      return false;
    }
    return button.classList.contains("active")
      || button.getAttribute("aria-pressed") === "true"
      || normalizeText(button.getAttribute("data-active")).toLowerCase() === "true";
  }

  function findG5ProviderButton() {
    return document.querySelector('button.provider-option[data-provider="gmail500"]')
      || document.querySelector('[data-provider="gmail500"]')
      || toArray(document.querySelectorAll("button")).find(function (node) {
        var onclickText = normalizeText(node.getAttribute("onclick") || "").toLowerCase();
        var text = normalizeText(node.innerText || node.textContent || "").toLowerCase();
        return onclickText.indexOf("setemailprovider('gmail500')") >= 0
          || onclickText.indexOf('setemailprovider("gmail500")') >= 0
          || text === "g5";
      }) || null;
  }

  function lockProviderToG5() {
    var button = findG5ProviderButton();
    if (!button) {
      return false;
    }
    if (isG5ProviderActive(button)) {
      return true;
    }
    return clickElement(button);
  }

  async function checkProviderLock() {
    var config = await getStoredConfig();
    if (!config.lockG5) {
      return;
    }
    lockProviderToG5();
  }

  function scheduleProviderLock() {
    window.setTimeout(function () {
      checkProviderLock();
    }, 250);
  }

  function startProviderLockPoll() {
    if (providerLockTimer) {
      return;
    }
    providerLockTimer = window.setInterval(function () {
      checkProviderLock();
    }, PROVIDER_LOCK_POLL_MS);
    scheduleProviderLock();
  }

  function getCodeTextForRow(rowId, displayAttribute) {
    var selectors = [
      '.twofa-code-display[' + displayAttribute + '="' + rowId + '"] .twofa-code',
      '.twofa-code-display[' + displayAttribute + '="' + rowId + '"]',
      '[' + displayAttribute + '="' + rowId + '"] .twofa-code',
      '[' + displayAttribute + '="' + rowId + '"]',
    ];
    var i;
    for (i = 0; i < selectors.length; i += 1) {
      var node = document.querySelector(selectors[i]);
      if (!node) {
        continue;
      }
      var text = normalizeText(node.innerText || node.textContent || "");
      var match = text.match(/\b(\d{6})\b/);
      if (match) {
        return match[1];
      }
    }
    return "";
  }

  function getOtpTextForRow(rowId) {
    return getCodeTextForRow(rowId, "data-code-display");
  }

  function getSmsTextForRow(rowId) {
    return getCodeTextForRow(rowId, "data-sms-display");
  }

  function isVisibleElement(node) {
    var style;
    var rect;
    if (!node || node.nodeType !== 1) {
      return false;
    }
    try {
      style = window.getComputedStyle(node);
      if (!style || style.display === "none" || style.visibility === "hidden" || Number(style.opacity || 1) === 0) {
        return false;
      }
      rect = node.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    } catch (_error) {
      return false;
    }
  }

  function getOtpPopupCandidates() {
    var selectors = [
      ".toast",
      ".Toastify__toast",
      ".swal2-popup",
      ".alert",
      ".notification",
      ".notyf__toast",
      ".Vue-Toastification__toast",
      "[role='alert']",
      "[aria-live]",
      "[class*='toast' i]",
      "[class*='notif' i]",
      "[class*='alert' i]",
      "[class*='snackbar' i]",
    ];
    var seen = [];
    var candidates = [];

    selectors.forEach(function (selector) {
      var nodes;
      try {
        nodes = toArray(document.querySelectorAll(selector));
      } catch (_error) {
        nodes = [];
      }

      nodes.forEach(function (node) {
        var text;
        var match;
        if (seen.indexOf(node) >= 0 || !isVisibleElement(node)) {
          return;
        }
        seen.push(node);
        text = normalizeText(node.innerText || node.textContent || "");
        if (!/\bcode\b/i.test(text)) {
          return;
        }
        match = text.match(/\b(\d{6})\b/);
        if (match) {
          candidates.push({
            node: node,
            text: text,
            code: match[1],
          });
        }
      });
    });

    return candidates;
  }

  function captureOtpPopupSnapshot() {
    var snapshot = {
      nodes: [],
      texts: {},
    };

    getOtpPopupCandidates().forEach(function (candidate) {
      snapshot.nodes.push(candidate.node);
      snapshot.texts[candidate.text] = true;
    });

    return snapshot;
  }

  function getNewOtpPopupCode(snapshot) {
    var prior = snapshot || { nodes: [], texts: {} };
    var candidates = getOtpPopupCandidates();
    var i;
    var candidate;

    for (i = 0; i < candidates.length; i += 1) {
      candidate = candidates[i];
      if (prior.nodes.indexOf(candidate.node) < 0 || !prior.texts[candidate.text]) {
        return candidate.code;
      }
    }

    return "";
  }

  function clickCheckCode(rowId) {
    var button = document.querySelector('button.btn-check-code[data-check-code="' + rowId + '"]')
      || document.querySelector('button[data-check-code="' + rowId + '"]');
    if (!button) {
      button = toArray(document.querySelectorAll("button")).find(function (node) {
        var onclickText = String(node.getAttribute("onclick") || "");
        return onclickText.indexOf("check2faCode") >= 0 && onclickText.indexOf(rowId) >= 0;
      }) || null;
    }
    if (!button) {
      return false;
    }
    button.click();
    return true;
  }

  function clickCheckSms(rowId) {
    var button = document.querySelector('button.btn-check-code[data-check-sms="' + rowId + '"]')
      || document.querySelector('button[data-check-sms="' + rowId + '"]');
    if (!button) {
      button = toArray(document.querySelectorAll("button")).find(function (node) {
        var onclickText = String(node.getAttribute("onclick") || "");
        return onclickText.indexOf("checkSms") >= 0 && onclickText.indexOf(rowId) >= 0;
      }) || null;
    }
    if (!button) {
      return false;
    }
    button.click();
    return true;
  }

  function clickGetEmailButton(rowId) {
    var button = document.querySelector('button.btn-get-email[data-get-email="' + rowId + '"]')
      || document.querySelector('button[data-get-email="' + rowId + '"]');
    if (!button) {
      button = toArray(document.querySelectorAll("button")).find(function (node) {
        var onclickText = String(node.getAttribute("onclick") || "");
        return onclickText.indexOf("get2faEmail") >= 0 && onclickText.indexOf(rowId) >= 0;
      }) || null;
    }
    if (!button) {
      return false;
    }
    return clickElement(button);
  }

  function clickGetPhoneButton(rowId) {
    var button = document.querySelector('button.btn-get-email[data-get-phone="' + rowId + '"]')
      || document.querySelector('button[data-get-phone="' + rowId + '"]');
    if (!button) {
      button = toArray(document.querySelectorAll("button")).find(function (node) {
        var onclickText = String(node.getAttribute("onclick") || "");
        var title = normalizeText(node.getAttribute("title") || "").toLowerCase();
        return onclickText.indexOf("getPhone") >= 0 && onclickText.indexOf(rowId) >= 0
          || (title.indexOf("request phone") >= 0 && onclickText.indexOf(rowId) >= 0);
      }) || null;
    }
    if (!button) {
      return false;
    }
    return clickElement(button);
  }

  function clickRedoEmailButton(rowId) {
    var button = document.querySelector('button.btn-redo-email[data-redo-email="' + rowId + '"]')
      || document.querySelector('button[data-redo-email="' + rowId + '"]');
    if (!button) {
      button = toArray(document.querySelectorAll("button")).find(function (node) {
        var onclickText = String(node.getAttribute("onclick") || "");
        var title = normalizeText(node.getAttribute("title") || "").toLowerCase();
        return onclickText.indexOf("redo2faEmail") >= 0 && onclickText.indexOf(rowId) >= 0
          || (title.indexOf("get new email") >= 0 && onclickText.indexOf(rowId) >= 0);
      }) || null;
    }
    if (!button) {
      return false;
    }
    return clickElement(button);
  }

  function clickRedoPhoneButton(rowId) {
    var button = document.querySelector('button.btn-redo-email[data-redo-phone="' + rowId + '"]')
      || document.querySelector('button[data-redo-phone="' + rowId + '"]');
    if (!button) {
      button = toArray(document.querySelectorAll("button")).find(function (node) {
        var onclickText = String(node.getAttribute("onclick") || "");
        var title = normalizeText(node.getAttribute("title") || "").toLowerCase();
        return onclickText.indexOf("redoPhone") >= 0 && onclickText.indexOf(rowId) >= 0
          || (title.indexOf("get new number") >= 0 && onclickText.indexOf(rowId) >= 0);
      }) || null;
    }
    if (!button) {
      return false;
    }
    return clickElement(button);
  }

  function waitForEmailForRow(rowId, timeoutMs, previousEmail) {
    return new Promise(function (resolve) {
      var startedAt = Date.now();
      var observer = null;
      var timer = null;
      var finished = false;
      var prior = normalizeComparableEmail(previousEmail);

      function cleanup(result) {
        if (finished) {
          return;
        }
        finished = true;
        if (observer) {
          observer.disconnect();
        }
        if (timer) {
          window.clearInterval(timer);
        }
        resolve(result || "");
      }

      function checkNow() {
        var email = readEmailFromRowId(rowId);
        if (email && normalizeComparableEmail(email) !== prior) {
          cleanup(email);
          return true;
        }
        if (email && !prior) {
          cleanup(email);
          return true;
        }
        if ((Date.now() - startedAt) >= timeoutMs) {
          cleanup("");
          return true;
        }
        return false;
      }

      if (checkNow()) {
        return;
      }

      var row = document.querySelector('tr[data-id="' + rowId + '"]');
      if (row && typeof MutationObserver !== "undefined") {
        observer = new MutationObserver(checkNow);
        observer.observe(row, {
          childList: true,
          subtree: true,
          characterData: true,
          attributes: true,
        });
      }

      timer = window.setInterval(checkNow, 350);
    });
  }

  function waitForPhoneForRow(rowId, timeoutMs, previousPhone) {
    return new Promise(function (resolve) {
      var startedAt = Date.now();
      var observer = null;
      var timer = null;
      var finished = false;
      var prior = normalizeText(previousPhone);

      function cleanup(result) {
        if (finished) {
          return;
        }
        finished = true;
        if (observer) {
          observer.disconnect();
        }
        if (timer) {
          window.clearInterval(timer);
        }
        resolve(result || "");
      }

      function checkNow() {
        var phone = readPhoneFromRowId(rowId);
        if (phone && phone !== prior) {
          cleanup(phone);
          return true;
        }
        if (phone && !prior) {
          cleanup(phone);
          return true;
        }
        if ((Date.now() - startedAt) >= timeoutMs) {
          cleanup("");
          return true;
        }
        return false;
      }

      if (checkNow()) {
        return;
      }

      var row = document.querySelector('tr[data-id="' + rowId + '"]');
      if (row && typeof MutationObserver !== "undefined") {
        observer = new MutationObserver(checkNow);
        observer.observe(row, {
          childList: true,
          subtree: true,
          characterData: true,
          attributes: true,
        });
      }

      timer = window.setInterval(checkNow, 350);
    });
  }

  function hasNoPendingOrderToast(kind) {
    var text = "";
    try {
      text = normalizeText(document.body ? (document.body.innerText || document.body.textContent || "") : "").toLowerCase();
    } catch (e) {
      text = "";
    }
    if (kind === "phone") {
      // "No pending phone order for this account. Request a number first."
      return text.indexOf("no pending phone order") >= 0
        || text.indexOf("no pending order") >= 0
        || text.indexOf("request a number first") >= 0
        || text.indexOf("get a number first") >= 0
        || text.indexOf("get number first") >= 0;
    }
    // "No pending email order for this account. Get email first."
    return text.indexOf("no pending email order") >= 0
      || text.indexOf("no pending order") >= 0
      || text.indexOf("get email first") >= 0;
  }

  async function requestEmailFetch(rowId, forceNew) {
    var currentEmail = readEmailFromRowId(rowId);
    if (currentEmail && !forceNew) {
      return { ok: true, email: currentEmail };
    }

    var clicked = forceNew ? clickRedoEmailButton(rowId) : clickGetEmailButton(rowId);
    if (!clicked) {
      // Fall back to the other button so a missing Redo (or Get) button still
      // orders an email instead of failing outright.
      clicked = forceNew ? clickGetEmailButton(rowId) : clickRedoEmailButton(rowId);
    }
    if (!clicked) {
      return { ok: false, error: "No Get/Redo Email button found for row." };
    }

    var fetchedEmail = await waitForEmailForRow(rowId, EMAIL_FETCH_TIMEOUT_MS, currentEmail);

    // "No pending email order for this account. Get email first." — SnapBoard
    // needs an email ordered before it will hand one over. Click Get Email and
    // wait again before giving up so the Python side can keep proceeding.
    if (!fetchedEmail && hasNoPendingOrderToast("email")) {
      if (clickGetEmailButton(rowId)) {
        fetchedEmail = await waitForEmailForRow(rowId, EMAIL_FETCH_TIMEOUT_MS, currentEmail);
      }
    }

    if (!fetchedEmail) {
      return {
        ok: false,
        // Signals the background to refresh SnapBoard and retry — a stale board
        // is a common cause of "no pending order" when an order really exists.
        stale: hasNoPendingOrderToast("email"),
        error: forceNew
          ? "New email did not appear after clicking Redo Email."
          : "Email did not appear after clicking Get Email.",
      };
    }

    queueScan();
    return { ok: true, email: fetchedEmail };
  }

  async function requestPhoneFetch(rowId, forceNew) {
    var currentPhone = readPhoneFromRowId(rowId);
    if (currentPhone && !forceNew) {
      return { ok: true, phone: currentPhone };
    }

    var clicked = forceNew ? clickRedoPhoneButton(rowId) : clickGetPhoneButton(rowId);
    if (!clicked) {
      clicked = forceNew ? clickGetPhoneButton(rowId) : clickRedoPhoneButton(rowId);
    }
    if (!clicked) {
      return { ok: false, error: "No Request/Redo Phone button found for row." };
    }

    var fetchedPhone = await waitForPhoneForRow(rowId, EMAIL_FETCH_TIMEOUT_MS, currentPhone);

    // "No pending phone order for this account. Request a number first." —
    // SnapBoard needs a number ordered before it hands one over. Mirror the
    // email path: click Request Number and wait again before giving up.
    if (!fetchedPhone && hasNoPendingOrderToast("phone")) {
      if (clickGetPhoneButton(rowId)) {
        fetchedPhone = await waitForPhoneForRow(rowId, EMAIL_FETCH_TIMEOUT_MS, currentPhone);
      }
    }

    if (!fetchedPhone) {
      return {
        ok: false,
        stale: hasNoPendingOrderToast("phone"),
        error: forceNew
          ? "New phone did not appear after clicking Redo Phone."
          : "Phone did not appear after clicking Request Number.",
      };
    }

    queueScan();
    return { ok: true, phone: fetchedPhone };
  }

  function sleep(ms) {
    return new Promise(function (resolve) {
      window.setTimeout(resolve, ms);
    });
  }

  function setElementValue(node, value) {
    if (!node) {
      return false;
    }
    try {
      node.focus();
      if ("value" in node) {
        var proto = node.tagName === "TEXTAREA"
          ? window.HTMLTextAreaElement.prototype
          : window.HTMLInputElement.prototype;
        var descriptor = Object.getOwnPropertyDescriptor(proto, "value");
        if (descriptor && descriptor.set) {
          descriptor.set.call(node, value);
        } else {
          node.value = value;
        }
      } else {
        node.textContent = value;
      }
      node.dispatchEvent(new Event("input", { bubbles: true }));
      node.dispatchEvent(new Event("change", { bubbles: true }));
      // Many SnapBoard cells persist on blur, not just change. Firing
      // both ensures the row updates without a manual refresh.
      try {
        node.dispatchEvent(new FocusEvent("blur", { bubbles: true }));
      } catch (_blurError) {
        node.dispatchEvent(new Event("blur", { bubbles: true }));
      }
      try {
        node.dispatchEvent(new KeyboardEvent("keyup", { bubbles: true, key: "Tab" }));
      } catch (_kbError) {}
      return true;
    } catch (_error) {
      return false;
    }
  }

  function buttonMatchesSaveIntent(button) {
    var text = normalizeText(button.innerText || button.textContent || "").toLowerCase();
    var title = normalizeText(button.getAttribute("title") || "").toLowerCase();
    var label = normalizeText(button.getAttribute("aria-label") || "").toLowerCase();
    var hint = [text, title, label].join(" ");
    return hint.indexOf("save") >= 0
      || hint.indexOf("update") >= 0
      || hint.indexOf("confirm") >= 0
      || hint.indexOf("done") >= 0
      || hint === "ok"
      || text === "✓";
  }

  function callPageUpdateField(rowId, field, value) {
    // Content scripts run in an isolated world and cannot invoke the page's
    // inline handlers (onchange="updateField(...)") or `window.updateField`
    // directly. Injecting a <script> tag runs in the page world, which does
    // have access to the SnapBoard app's functions and state.
    //
    // We also schedule two re-applications (~120ms and ~400ms later)
    // because SnapBoard re-renders the row from its in-memory state right
    // after updateField saves to the server, which can blank the visible
    // input until the next manual page refresh.
    try {
      var script = document.createElement("script");
      script.textContent =
        "(function(){try{" +
        "var rid=" + JSON.stringify(String(rowId)) + ";" +
        "var field=" + JSON.stringify(String(field)) + ";" +
        "var value=" + JSON.stringify(String(value)) + ";" +
        "function applyValue(){try{" +
          "var row=document.querySelector('tr[data-id=\"'+rid+'\"]');" +
          "var input=row?row.querySelector('input.input-'+field)" +
          "||row.querySelector('input[onchange*=\"'+field+'\"]'):null;" +
          "if(input&&input.value!==value){" +
            "var p=input.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;" +
            "var d=Object.getOwnPropertyDescriptor(p,'value');" +
            "if(d&&d.set){d.set.call(input,value);}else{input.value=value;}" +
            "input.dispatchEvent(new Event('input',{bubbles:true}));" +
            "input.dispatchEvent(new Event('change',{bubbles:true}));" +
            "try{input.dispatchEvent(new FocusEvent('blur',{bubbles:true}));}catch(_b){" +
            "input.dispatchEvent(new Event('blur',{bubbles:true}));}" +
          "}" +
        "}catch(_e){}}" +
        "applyValue();" +
        "if(typeof updateField==='function'){try{updateField(rid,field,value);}catch(_u){}}" +
        // Re-assert after SnapBoard's post-save re-render so the cell
        // shows the new value without requiring a refresh.
        "setTimeout(applyValue,120);" +
        "setTimeout(applyValue,400);" +
        "}catch(e){}})();";
      (document.head || document.documentElement).appendChild(script);
      script.remove();
      return true;
    } catch (_error) {
      return false;
    }
  }

  function findRowInput(rowId, selectors) {
    var row = document.querySelector('tr[data-id="' + rowId + '"]');
    if (!row) {
      return null;
    }
    for (var i = 0; i < selectors.length; i += 1) {
      var node = row.querySelector(selectors[i]);
      if (node) {
        return node;
      }
    }
    return null;
  }

  var USERNAME_INPUT_SELECTORS = [
    "input.cell-input.input-username",
    "input.input-username",
    "input[placeholder='username']",
    "input[onchange*=\"updateField\"][onchange*=\"username\"]",
  ];

  var ADSPOWER_INPUT_SELECTORS = [
    "input.cell-input.input-adspower",
    "input.input-adspower",
    "input[onchange*=\"updateField\"][onchange*=\"adspowerId\"]",
    "input[placeholder='ID']",
  ];

  var ADSPOWER_NAME_INPUT_SELECTORS = [
    "input.cell-input.input-adspowerName",
    "input.input-adspowerName",
    "input.cell-input.input-adspower-name",
    "input.input-adspower-name",
    "input.cell-input.input-name",
    "input.input-name",
    "input[onchange*=\"updateField\"][onchange*=\"adspowerName\"]",
    "input[onchange*=\"updateField\"][onchange*=\"name\"]",
    "input[placeholder*='name' i]",
  ];

  // Sync write so the bridge poll cycle (OTP, username, proxy, adspower)
  // stays snappy — a slow update here used to starve OTP auto-check.
  // callPageUpdateField schedules two re-applications at +120ms and +400ms
  // inside SnapBoard's own page world, which catches its post-save
  // re-render so the cell shows the new value without a refresh.
  function requestUsernameUpdate(rowId, username) {
    var input = findRowInput(rowId, USERNAME_INPUT_SELECTORS)
      || (function () {
        var row = document.querySelector('tr[data-id="' + rowId + '"]');
        return row ? (row.querySelector("input, textarea")) : null;
      })();
    if (!input) {
      return false;
    }

    setElementValue(input, username);
    callPageUpdateField(rowId, "username", username);

    return normalizeText(input.value || "") === normalizeText(username);
  }

  function requestAdspowerIdUpdate(rowId, adspowerId) {
    var input = findRowInput(rowId, ADSPOWER_INPUT_SELECTORS);
    if (!input) {
      return false;
    }

    setElementValue(input, adspowerId);
    callPageUpdateField(rowId, "adspowerId", adspowerId);

    return normalizeText(input.value || "") === normalizeText(adspowerId);
  }

  function requestAdspowerNameUpdate(rowId, adspowerName) {
    var input = findRowInput(rowId, ADSPOWER_NAME_INPUT_SELECTORS);
    if (!input) {
      return false;
    }

    setElementValue(input, adspowerName);
    callPageUpdateField(rowId, "adspowerName", adspowerName);
    callPageUpdateField(rowId, "name", adspowerName);

    return normalizeText(input.value || "") === normalizeText(adspowerName);
  }

  // Set a SnapBoard row's status cell (the <select class="status-select">).
  // Used to mark accounts as "Banned" when the Bitmoji bot hits a Snapchat
  // authorization error. SnapBoard attaches a change listener to the select
  // (there is no inline onchange), so dispatching a native change event after
  // setting the value persists the new status without a manual refresh.
  function setRowStatus(rowId, status) {
    var desired = normalizeText(status);
    if (!desired) {
      return false;
    }
    var row = document.querySelector('tr[data-id="' + rowId + '"]');
    if (!row) {
      return false;
    }
    var select = row.querySelector("select.cell-select.status-select")
      || row.querySelector("select.status-select")
      || toArray(row.querySelectorAll("select")).find(function (sel) {
        return toArray(sel.options || []).some(function (option) {
          return normalizeText(option.value) === desired;
        });
      });
    if (!select) {
      return false;
    }
    var hasOption = toArray(select.options || []).some(function (option) {
      return normalizeText(option.value) === desired;
    });
    if (!hasOption) {
      return false;
    }
    if (normalizeText(select.value) === desired) {
      return true;
    }
    select.value = desired;
    select.dispatchEvent(new Event("input", { bubbles: true }));
    select.dispatchEvent(new Event("change", { bubbles: true }));
    return normalizeText(select.value) === desired;
  }

  var proxyRotatePollInFlight = false;

  function clickRotateButton(rowId) {
    var row = document.querySelector('tr[data-id="' + rowId + '"]');
    if (!row) return false;
    var btn = row.querySelector(".btn-rotate")
      || row.querySelector('[data-action*="rotate" i]')
      || row.querySelector('[aria-label*="proxy" i]')
      || row.querySelector('[title*="proxy" i]')
      || row.querySelector('[title="Get new proxy"]')
      || toArray(row.querySelectorAll("button")).find(function (b) {
           return buttonMatchesRotateIntent(b);
         })
      || toArray(row.querySelectorAll("[role='button'], a, div")).find(function (b) {
           return buttonMatchesRotateIntent(b);
         }) || null;
    if (btn) { return clickElement(btn); }
    if (typeof window.rotateProxy === "function") { window.rotateProxy(rowId); return true; }
    return false;
  }

  function readProxyFromRow(rowId) {
    var row = document.querySelector('tr[data-id="' + rowId + '"]');
    if (!row) return "";
    var headerMap = getTableHeaderMap(row);
    return readValueFromAliases(row, headerMap, ["proxy", "proxy address", "ip address", "ip"]);
  }

  async function pollPendingProxyRotation() {
    if (proxyRotatePollInFlight) return;
    proxyRotatePollInFlight = true;
    try {
      var config = await getStoredConfig();
      var apiConfig = getLocalApiConfig(config);
      if (!apiConfig.localApiUrl) return;
      if (config.proxyBlockerEnabled === false && config.proxyCheckerEnabled === false) return;

      var headers = {};
      if (apiConfig.localToken) headers["X-Nyxify-Token"] = apiConfig.localToken;

      var response = await fetch(apiConfig.localApiUrl + "/proxy/rotate_pending", {
        method: "GET", headers: headers,
      });
      var payload = await response.json();
      if (!response.ok || !payload.ok || !payload.row_key) return;

      var rowKey = normalizeText(payload.row_key);
      var rowId = extractRowId(rowKey);
      if (!rowId) return;

      // Use the same robust multi-click rotate as the manual path: click the
      // rotate button up to maxClicks times and wait PROXY_ROTATE_WAIT_MS for the
      // proxy cell to actually change. The single-click / 16s wait this replaced
      // reported "did not change" when SnapBoard simply took longer than 16s to
      // swap the proxy, which read to the runner as a failed rotation.
      var maxClicks = parseInt(payload.max_clicks, 10);
      if (!(maxClicks >= 1)) maxClicks = 3;

      var result = await rotateProxyUntilChanged(rowId, PROXY_ROTATE_WAIT_MS, maxClicks);

      headers["Content-Type"] = "application/json";
      if (result && result.ok && result.proxy) {
        await fetch(apiConfig.localApiUrl + "/proxy/rotate_result", {
          method: "POST", headers: headers,
          body: JSON.stringify({ row_key: rowKey, proxy: result.proxy }),
        });
      } else {
        await fetch(apiConfig.localApiUrl + "/proxy/rotate_result", {
          method: "POST", headers: headers,
          body: JSON.stringify({ row_key: rowKey, error: (result && result.error) || "Proxy did not change after rotation" }),
        });
      }
    } catch (error) {
      return;
    } finally {
      proxyRotatePollInFlight = false;
    }
  }

  function waitForProxyChange(rowId, oldProxy, timeoutMs) {
    return new Promise(function (resolve) {
      var start = Date.now();
      var finished = false;
      var observer = null;
      var timer = null;

      function cleanup(result) {
        if (finished) {
          return;
        }
        finished = true;
        if (observer) {
          observer.disconnect();
        }
        if (timer) {
          window.clearInterval(timer);
        }
        resolve(result || "");
      }

      function checkNow() {
        var latest = readProxyFromRow(rowId);
        if (latest && latest !== oldProxy) {
          cleanup(latest);
          return true;
        }
        if ((Date.now() - start) >= timeoutMs) {
          cleanup("");
          return true;
        }
        return false;
      }

      if (checkNow()) {
        return;
      }

      var row = document.querySelector('tr[data-id="' + rowId + '"]');
      if (row && typeof MutationObserver !== "undefined") {
        observer = new MutationObserver(checkNow);
        observer.observe(row, {
          childList: true,
          subtree: true,
          characterData: true,
        });
      }

      timer = window.setInterval(checkNow, 350);
    });
  }

  function waitForOtpCode(rowId, timeoutMs, popupSnapshot) {
    return new Promise(function (resolve) {
      var startedAt = Date.now();
      var observer = null;
      var timer = null;
      var finished = false;

      function cleanup(result) {
        if (finished) {
          return;
        }
        finished = true;
        if (observer) {
          observer.disconnect();
        }
        if (timer) {
          window.clearInterval(timer);
        }
        resolve(result || "");
      }

      function checkNow() {
        var code = getOtpTextForRow(rowId) || getNewOtpPopupCode(popupSnapshot);
        if (code) {
          cleanup(code);
          return true;
        }
        if ((Date.now() - startedAt) >= timeoutMs) {
          cleanup("");
          return true;
        }
        return false;
      }

      if (checkNow()) {
        return;
      }

      var row = document.querySelector('tr[data-id="' + rowId + '"]');
      if (typeof MutationObserver !== "undefined") {
        observer = new MutationObserver(checkNow);
        if (row) {
          observer.observe(row, {
            childList: true,
            subtree: true,
            characterData: true,
          });
        }
        if (document.body) {
          observer.observe(document.body, {
            childList: true,
            subtree: true,
            characterData: true,
          });
        }
      }

      timer = window.setInterval(checkNow, 250);
    });
  }

  function waitForSmsCode(rowId, timeoutMs, popupSnapshot) {
    return new Promise(function (resolve) {
      var startedAt = Date.now();
      var observer = null;
      var timer = null;
      var finished = false;

      function cleanup(result) {
        if (finished) {
          return;
        }
        finished = true;
        if (observer) {
          observer.disconnect();
        }
        if (timer) {
          window.clearInterval(timer);
        }
        resolve(result || "");
      }

      function checkNow() {
        var code = getSmsTextForRow(rowId) || getNewOtpPopupCode(popupSnapshot);
        if (code) {
          cleanup(code);
          return true;
        }
        if ((Date.now() - startedAt) >= timeoutMs) {
          cleanup("");
          return true;
        }
        return false;
      }

      if (checkNow()) {
        return;
      }

      var row = document.querySelector('tr[data-id="' + rowId + '"]');
      if (typeof MutationObserver !== "undefined") {
        observer = new MutationObserver(checkNow);
        if (row) {
          observer.observe(row, {
            childList: true,
            subtree: true,
            characterData: true,
          });
        }
        if (document.body) {
          observer.observe(document.body, {
            childList: true,
            subtree: true,
            characterData: true,
          });
        }
      }

      timer = window.setInterval(checkNow, 250);
    });
  }

  async function clickCheckCodeUntilOtp(rowId, timeoutMs) {
    var startedAt = Date.now();
    var latestCode = getOtpTextForRow(rowId);
    var popupSnapshot = captureOtpPopupSnapshot();
    while (!latestCode && (Date.now() - startedAt) < timeoutMs) {
      clickCheckCode(rowId);
      latestCode = await waitForOtpCode(
        rowId,
        Math.min(OTP_CLICK_RETRY_INTERVAL_MS, Math.max(500, timeoutMs - (Date.now() - startedAt))),
        popupSnapshot
      );
      if (latestCode) {
        return latestCode;
      }
      await sleep(300);
    }
    return latestCode || "";
  }

  async function clickCheckSmsUntilOtp(rowId, timeoutMs) {
    var startedAt = Date.now();
    var latestCode = getSmsTextForRow(rowId);
    var popupSnapshot = captureOtpPopupSnapshot();
    while (!latestCode && (Date.now() - startedAt) < timeoutMs) {
      clickCheckSms(rowId);
      latestCode = await waitForSmsCode(
        rowId,
        Math.min(OTP_CLICK_RETRY_INTERVAL_MS, Math.max(500, timeoutMs - (Date.now() - startedAt))),
        popupSnapshot
      );
      if (latestCode) {
        return latestCode;
      }
      await sleep(300);
    }
    return latestCode || "";
  }

  async function rotateProxyUntilChanged(rowId, timeoutMs, maxClicks) {
    var oldProxy = readProxyFromRow(rowId);
    var attempt = 0;
    while (attempt < maxClicks) {
      attempt += 1;
      var clicked = clickRotateButton(rowId);
      if (!clicked) {
        if (attempt >= maxClicks) {
          return { ok: false, error: "No rotate button found for row." };
        }
        await sleep(400);
        continue;
      }
      var newProxy = await waitForProxyChange(rowId, oldProxy, timeoutMs);
      if (newProxy && newProxy !== oldProxy) {
        return { ok: true, proxy: newProxy };
      }
      await sleep(600);
    }
    return { ok: false, error: "Proxy did not change after rotation." };
  }

  async function pollPendingOtpRequest() {
    if (otpPollInFlight) {
      return;
    }
    otpPollInFlight = true;

    try {
      var config = await getStoredConfig();
      var apiConfig = getLocalApiConfig(config);
      if (!apiConfig.localApiUrl) {
        return;
      }

      var headers = {};
      if (apiConfig.localToken) {
        headers["X-Nyxify-Token"] = apiConfig.localToken;
      }

      var response = await fetch(apiConfig.localApiUrl + "/otp/pending", {
        method: "GET",
        headers: headers,
      });
      var payload = await response.json();
      if (!response.ok || !payload.ok || !payload.request) {
        return;
      }

      var rowKey = normalizeText(payload.request.row_key);
      var rowId = extractRowId(rowKey);
      if (!rowId) {
        return;
      }
      if (!rowMatchesExpectedEmail(rowId, payload.request.email)) {
        return;
      }

      var code = await clickCheckCodeUntilOtp(rowId, OTP_FETCH_TIMEOUT_MS);
      if (!code) {
        return;
      }

      headers["Content-Type"] = "application/json";
      await fetch(apiConfig.localApiUrl + "/otp/result", {
        method: "POST",
        headers: headers,
        body: JSON.stringify({
          row_key: rowKey,
          code: code,
        }),
      });
    } catch (error) {
      return;
    } finally {
      otpPollInFlight = false;
    }
  }

  async function pollPendingUsernameUpdate() {
    if (usernameUpdatePollInFlight) {
      return;
    }
    usernameUpdatePollInFlight = true;

    try {
      var config = await getStoredConfig();
      var apiConfig = getLocalApiConfig(config);
      if (!apiConfig.localApiUrl) {
        return;
      }

      var headers = {};
      if (apiConfig.localToken) {
        headers["X-Nyxify-Token"] = apiConfig.localToken;
      }

      var response = await fetch(apiConfig.localApiUrl + "/username_update/pending", {
        method: "GET",
        headers: headers,
      });
      var payload = await response.json();
      if (!response.ok || !payload.ok || !payload.request) {
        return;
      }

      var rowKey = normalizeText(payload.request.row_key);
      var nextUsername = normalizeText(payload.request.username);
      var updated = requestUsernameUpdate(
        rowKey.replace(/^snapboard:/i, ""),
        nextUsername
      );

      headers["Content-Type"] = "application/json";
      await fetch(apiConfig.localApiUrl + "/username_update/result", {
        method: "POST",
        headers: headers,
        body: JSON.stringify({
          row_key: rowKey,
          success: updated,
          error: updated ? "" : "SnapBoard username input was not updated",
        }),
      });
    } catch (_error) {
      return;
    } finally {
      usernameUpdatePollInFlight = false;
    }
  }

  async function pollPendingAdspowerUpdate() {
    if (adspowerUpdatePollInFlight) {
      return;
    }
    adspowerUpdatePollInFlight = true;

    try {
      var config = await getStoredConfig();
      var apiConfig = getLocalApiConfig(config);
      if (!apiConfig.localApiUrl) {
        return;
      }

      var headers = {};
      if (apiConfig.localToken) {
        headers["X-Nyxify-Token"] = apiConfig.localToken;
      }

      var response = await fetch(apiConfig.localApiUrl + "/adspower_update/pending", {
        method: "GET",
        headers: headers,
      });
      var payload = await response.json();
      if (!response.ok || !payload.ok || !payload.request) {
        return;
      }

      var rowKey = normalizeText(payload.request.row_key);
      var nextAdspowerId = normalizeText(payload.request.adspower_id);
      var updated = requestAdspowerIdUpdate(
        rowKey.replace(/^snapboard:/i, ""),
        nextAdspowerId
      );

      headers["Content-Type"] = "application/json";
      await fetch(apiConfig.localApiUrl + "/adspower_update/result", {
        method: "POST",
        headers: headers,
        body: JSON.stringify({
          row_key: rowKey,
          success: updated,
          error: updated ? "" : "SnapBoard AdsPower id input was not updated",
        }),
      });
    } catch (_error) {
      return;
    } finally {
      adspowerUpdatePollInFlight = false;
    }
  }

  async function pollPendingAdspowerNameUpdate() {
    if (adspowerNameUpdatePollInFlight) {
      return;
    }
    adspowerNameUpdatePollInFlight = true;

    try {
      var config = await getStoredConfig();
      var apiConfig = getLocalApiConfig(config);
      if (!apiConfig.localApiUrl) {
        return;
      }

      var headers = {};
      if (apiConfig.localToken) {
        headers["X-Nyxify-Token"] = apiConfig.localToken;
      }

      var response = await fetch(apiConfig.localApiUrl + "/adspower_name_update/pending", {
        method: "GET",
        headers: headers,
      });
      var payload = await response.json();
      if (!response.ok || !payload.ok || !payload.request) {
        return;
      }

      var rowKey = normalizeText(payload.request.row_key);
      var nextName = normalizeText(payload.request.adspower_name);
      var updated = requestAdspowerNameUpdate(
        rowKey.replace(/^snapboard:/i, ""),
        nextName
      );

      headers["Content-Type"] = "application/json";
      await fetch(apiConfig.localApiUrl + "/adspower_name_update/result", {
        method: "POST",
        headers: headers,
        body: JSON.stringify({
          row_key: rowKey,
          success: updated,
          error: updated ? "" : "SnapBoard AdsPower name input was not updated",
        }),
      });
    } catch (_error) {
      return;
    } finally {
      adspowerNameUpdatePollInFlight = false;
    }
  }

  async function pollPendingStatusUpdate() {
    if (statusUpdatePollInFlight) {
      return;
    }
    statusUpdatePollInFlight = true;

    try {
      var config = await getStoredConfig();
      var apiConfig = getLocalApiConfig(config);
      if (!apiConfig.localApiUrl) {
        return;
      }

      var headers = {};
      if (apiConfig.localToken) {
        headers["X-Nyxify-Token"] = apiConfig.localToken;
      }

      var response = await fetch(apiConfig.localApiUrl + "/status_update/pending", {
        method: "GET",
        headers: headers,
      });
      var payload = await response.json();
      if (!response.ok || !payload.ok || !payload.request) {
        return;
      }

      var rowKey = normalizeText(payload.request.row_key);
      var nextStatus = normalizeText(payload.request.status);
      var updated = setRowStatus(
        rowKey.replace(/^snapboard:/i, ""),
        nextStatus
      );

      headers["Content-Type"] = "application/json";
      await fetch(apiConfig.localApiUrl + "/status_update/result", {
        method: "POST",
        headers: headers,
        body: JSON.stringify({
          row_key: rowKey,
          success: updated,
          error: updated ? "" : "SnapBoard status cell was not updated",
        }),
      });
    } catch (_error) {
      return;
    } finally {
      statusUpdatePollInFlight = false;
    }
  }

  function startStatusUpdatePoll() {
    if (statusUpdatePollTimer) {
      return;
    }
    statusUpdatePollTimer = window.setInterval(function () {
      pollPendingStatusUpdate();
    }, USERNAME_UPDATE_POLL_INTERVAL_MS);
  }

  function startUsernameUpdatePoll() {
    if (usernameUpdatePollTimer) {
      return;
    }
    usernameUpdatePollTimer = window.setInterval(function () {
      pollPendingUsernameUpdate();
    }, USERNAME_UPDATE_POLL_INTERVAL_MS);
  }

  function startAdspowerUpdatePoll() {
    if (adspowerUpdatePollTimer) {
      return;
    }
    adspowerUpdatePollTimer = window.setInterval(function () {
      pollPendingAdspowerUpdate();
    }, USERNAME_UPDATE_POLL_INTERVAL_MS);
  }

  function startAdspowerNameUpdatePoll() {
    if (adspowerNameUpdatePollTimer) {
      return;
    }
    adspowerNameUpdatePollTimer = window.setInterval(function () {
      pollPendingAdspowerNameUpdate();
    }, USERNAME_UPDATE_POLL_INTERVAL_MS);
  }

  function getReserveButton() {
    return document.getElementById("reserveBtn")
      || document.querySelector(".btn-reserve")
      || toArray(document.querySelectorAll("button")).find(function (b) {
           var onclick = normalizeText(b.getAttribute("onclick") || "").toLowerCase();
           return onclick.indexOf("reserveproxy") >= 0;
         }) || null;
  }

  function allRowsFilledNonePending() {
    var rows = toArray(document.querySelectorAll("tr[data-id]"));
    if (!rows.length) { return false; }
    var root = getRowRoot();
    var headerMap = getTableHeaderMap(root);
    for (var i = 0; i < rows.length; i++) {
      var adspowerId = normalizeText(readValueFromAliases(rows[i], headerMap, ["adspower", "adspower id", "profile id"]));
      if (!adspowerId) { return false; }
      var username = normalizeText(readValueFromAliases(rows[i], headerMap, ["username", "snap username", "snapchat username", "user", "snap user"]));
      if (!username) { return false; }
    }
    return true;
  }

  function reserveAutoFillClick() {
    return new Promise(function (resolve) {
      chrome.runtime.sendMessage({ type: "NYXIFY_AUTO_FILL_RESERVE_CLICK" }, function (response) {
        if (chrome.runtime.lastError) {
          resolve({ ok: false, error: chrome.runtime.lastError.message || "Auto-fill reservation failed." });
          return;
        }
        resolve(response || { ok: false, error: "Auto-fill reservation returned no response." });
      });
    });
  }

  async function checkAndAutoFill() {
    var config = await getStoredConfig();
    if (!config.autoFillRow) { return; }
    if (allRowsFilledNonePending()) {
      var btn = getReserveButton();
      if (!btn || btn.disabled) { return; }
      var reservation = await reserveAutoFillClick();
      if (reservation && reservation.ok && reservation.shouldClick) {
        clickElement(btn);
      }
    }
  }

  function startAutoFillPoll() {
    if (autoFillPollTimer) { return; }
    autoFillPollTimer = window.setInterval(function () { checkAndAutoFill(); }, AUTO_FILL_POLL_MS);
  }

  chrome.runtime.onMessage.addListener(function (message, _sender, sendResponse) {
    if (!message || message.type !== "NYXIFY_SNAPBOARD_ACTION") {
      return undefined;
    }

    (async function () {
      var rowKey = normalizeText(message.row_key);
      var rowId = extractRowId(rowKey);
      if (!rowId) {
        sendResponse({ ok: false, error: "Missing SnapBoard row id." });
        return;
      }

      if (message.action === "otp") {
        if (!rowMatchesExpectedEmail(rowId, message.email || message.expected_email)) {
          sendResponse({ ok: false, error: "SnapBoard row email does not match pending OTP account." });
          return;
        }
        var code = await clickCheckCodeUntilOtp(rowId, OTP_FETCH_TIMEOUT_MS);
        if (!code) {
          sendResponse({ ok: false, error: "OTP code not found on SnapBoard row." });
          return;
        }
        sendResponse({ ok: true, code: code });
        return;
      }

      if (message.action === "email_fetch") {
        var emailResult = await requestEmailFetch(rowId, !!message.force_new);
        sendResponse(emailResult);
        return;
      }

      if (message.action === "phone_fetch") {
        var phoneResult = await requestPhoneFetch(rowId, !!message.force_new);
        sendResponse(phoneResult);
        return;
      }

      if (message.action === "sms") {
        var smsCode = await clickCheckSmsUntilOtp(rowId, OTP_FETCH_TIMEOUT_MS);
        if (!smsCode) {
          sendResponse({ ok: false, error: "SMS code not found on SnapBoard row." });
          return;
        }
        sendResponse({ ok: true, code: smsCode });
        return;
      }

      if (message.action === "username_update") {
        var updated = requestUsernameUpdate(rowId, normalizeText(message.username));
        sendResponse({
          ok: updated,
          error: updated ? "" : "SnapBoard username input was not updated",
        });
        return;
      }

      if (message.action === "adspower_update") {
        var adsUpdated = requestAdspowerIdUpdate(rowId, normalizeText(message.adspower_id));
        sendResponse({
          ok: adsUpdated,
          error: adsUpdated ? "" : "SnapBoard AdsPower id input was not updated",
        });
        return;
      }

      if (message.action === "adspower_name_update") {
        var adsNameUpdated = requestAdspowerNameUpdate(rowId, normalizeText(message.adspower_name));
        sendResponse({
          ok: adsNameUpdated,
          error: adsNameUpdated ? "" : "SnapBoard AdsPower name input was not updated",
        });
        return;
      }

      if (message.action === "status_update") {
        var statusUpdated = setRowStatus(rowId, normalizeText(message.status));
        sendResponse({
          ok: statusUpdated,
          error: statusUpdated ? "" : "SnapBoard status cell was not updated",
        });
        return;
      }

      if (message.action === "proxy_rotate") {
        var requestedMaxClicks = parseInt(message.max_clicks, 10);
        var maxClicks = Number.isFinite(requestedMaxClicks) && requestedMaxClicks > 0
          ? requestedMaxClicks
          : PROXY_ROTATE_CLICK_ATTEMPTS;
        var proxyResult = await rotateProxyUntilChanged(rowId, PROXY_ROTATE_WAIT_MS, maxClicks);
        if (!proxyResult.ok) {
          sendResponse({ ok: false, error: proxyResult.error });
          return;
        }
        sendResponse({ ok: true, proxy: proxyResult.proxy });
        return;
      }

      sendResponse({ ok: false, error: "Unknown SnapBoard action." });
    })();

    return true;
  });

  document.addEventListener("input", queueScan, true);
  document.addEventListener("change", queueScan, true);
  document.addEventListener("click", queueScan, true);
  chrome.storage.onChanged.addListener(function (changes, areaName) {
    if (areaName !== "sync" || !changes[CONFIG_KEY]) {
      return;
    }
    configCache = changes[CONFIG_KEY].newValue || {};
    configCacheAt = Date.now();
    scheduleProviderLock();
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", queueScan, { once: true });
  } else {
    queueScan();
  }
  connectBridgePort();

  var observer = new MutationObserver(queueScan);
  observer.observe(document.documentElement || document.body, {
    childList: true,
    subtree: true,
    characterData: true,
  });

  startAutoFillPoll();
  startUsernameUpdatePoll();
  startAdspowerUpdatePoll();
  startAdspowerNameUpdatePoll();
  startStatusUpdatePoll();
  startProviderLockPoll();

})();
