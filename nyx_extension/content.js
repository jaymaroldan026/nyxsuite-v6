(function () {
  var debounceTimer = null;
  var CONFIG_KEY = "nyxConfig";
  var lastSentSignature = "";
  var lastBitmojiStatuses = [];

  function toArray(nodeList) {
    return Array.prototype.slice.call(nodeList || []);
  }

  function isPositiveNumber(value) {
    return typeof value === "number" && isFinite(value) && value > 0;
  }

  function normalizeText(value) {
    return String(value || "").trim();
  }

  function normalizeHeaderKey(value) {
    return normalizeText(value).toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  }

  function normalizeProfileId(value, options) {
    var trustedSource = !!(options && options.trustedSource);
    var normalized = normalizeText(value)
      .replace(/^adspower\s*id[:#-]?\s*/i, "")
      .replace(/^profile\s*id[:#-]?\s*/i, "")
      .trim();
    var lowered = normalized.toLowerCase();

    if (!normalized) {
      return "";
    }

    if (
      lowered === "id"
      || lowered === "adspower id"
      || lowered === "ads power id"
      || lowered === "profile id"
      || lowered === "n/a"
      || lowered === "na"
      || lowered === "none"
      || lowered === "null"
      || lowered === "undefined"
      || lowered === "-"
      || lowered === "--"
    ) {
      return "";
    }

    if (/^\d{4,}$/.test(normalized)) {
      return normalized;
    }

    if (trustedSource && /^[A-Za-z][A-Za-z0-9_-]{3,}$/.test(normalized)) {
      return normalized;
    }

    if (/^(?=.*\d)[A-Za-z0-9_-]{4,}$/.test(normalized)) {
      return normalized;
    }

    return "";
  }

  function getRowCells(row) {
    return toArray(row ? row.children : []).filter(function (cell) {
      return cell && (cell.tagName === "TD" || cell.tagName === "TH");
    });
  }

  function readCellText(cell) {
    var inputLike;
    var selectedOption;
    var textLikeNode;

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

    textLikeNode = cell.querySelector("[data-value], [role='combobox'], [role='textbox'], .selected, .value, .current");
    if (textLikeNode) {
      return normalizeText(
        textLikeNode.getAttribute("data-value")
        || textLikeNode.value
        || textLikeNode.textContent
        || ""
      );
    }

    return normalizeText(cell.textContent || "");
  }

  function getTableHeaderMap(tableBody) {
    var table;
    var headerCells;
    var headerMap = {};

    if (!tableBody) {
      return headerMap;
    }

    table = tableBody.closest("table");
    headerCells = toArray(
      (table && table.querySelectorAll("thead th")) ||
      document.querySelectorAll("thead th, table th")
    );

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
    var key;

    for (i = 0; i < aliases.length; i += 1) {
      key = normalizeHeaderKey(aliases[i]);
      if (Object.prototype.hasOwnProperty.call(headerMap, key)) {
        return headerMap[key];
      }
    }

    return -1;
  }

  function isStatusOptionValue(value) {
    var normalized = normalizeText(value).toLowerCase();
    return normalized === "warm up"
      || normalized === "banned"
      || normalized === "inaccessible"
      || normalized === "needs phone verification";
  }

  function isLikelyStatusSelect(select) {
    var options;

    if (!select) {
      return false;
    }

    if (select.classList && select.classList.contains("status-select")) {
      return true;
    }

    options = toArray(select.options || []);
    return options.length > 0 && options.every(function (option) {
      return isStatusOptionValue(option.value || option.textContent);
    });
  }

  function readSelectedModel(row, headerMap) {
    var modelSelect = row.querySelector("select.cell-select:not(.status-select)");
    var modelCellIndex;
    var rowCells;
    var selectedOption;
    var selectedValue;
    var modelCellValue;

    modelCellIndex = findHeaderIndex(headerMap || {}, ["model", "face model"]);
    if (modelCellIndex >= 0) {
      rowCells = getRowCells(row);
      if (rowCells[modelCellIndex]) {
        modelSelect = rowCells[modelCellIndex].querySelector("select.cell-select:not(.status-select)");
        if (modelSelect && !isLikelyStatusSelect(modelSelect)) {
          selectedOption = modelSelect.options[modelSelect.selectedIndex];
          selectedValue = selectedOption ? selectedOption.value : "";
          return normalizeText(selectedValue || modelSelect.value || (selectedOption && selectedOption.textContent) || "");
        }
        modelCellValue = readCellText(rowCells[modelCellIndex]);
        if (modelCellValue) {
          return modelCellValue;
        }
      }
    }

    if (!modelSelect) {
      return "";
    }

    selectedOption = modelSelect.options[modelSelect.selectedIndex];
    selectedValue = selectedOption ? selectedOption.value : "";
    return normalizeText(selectedValue || modelSelect.value || "");
  }

  function readUsername(row, headerMap) {
    var directInput = row.querySelector("input.input-username");
    var rowCells;
    var usernameCellIndex;

    if (directInput) {
      return normalizeText(directInput.value || directInput.getAttribute("value") || "");
    }

    usernameCellIndex = findHeaderIndex(headerMap || {}, ["username", "user name", "snapchat username"]);
    if (usernameCellIndex >= 0) {
      rowCells = getRowCells(row);
      if (rowCells[usernameCellIndex]) {
        return readCellText(rowCells[usernameCellIndex]);
      }
    }

    return "";
  }

  function getUsernameCell(row, headerMap) {
    var directInput = row.querySelector("input.input-username");
    var rowCells;
    var usernameCellIndex;

    if (directInput) {
      return directInput.closest("td, th") || directInput.parentElement || null;
    }

    usernameCellIndex = findHeaderIndex(headerMap || {}, ["username", "user name", "snapchat username"]);
    if (usernameCellIndex >= 0) {
      rowCells = getRowCells(row);
      if (rowCells[usernameCellIndex]) {
        return rowCells[usernameCellIndex];
      }
    }

    return null;
  }

  function readAdsPowerId(row, headerMap) {
    var directInput = row.querySelector("input.input-adspower");
    var rowCells;
    var profileCellIndex;
    var candidateValue;

    if (directInput && normalizeProfileId(directInput.value, { trustedSource: true })) {
      return normalizeProfileId(directInput.value, { trustedSource: true });
    }

    profileCellIndex = findHeaderIndex(headerMap || {}, ["adspower id", "ads power id", "profile id", "adspower"]);
    if (profileCellIndex >= 0) {
      rowCells = getRowCells(row);
      if (rowCells[profileCellIndex]) {
        candidateValue = readCellText(rowCells[profileCellIndex]);
        if (normalizeProfileId(candidateValue, { trustedSource: true })) {
          return normalizeProfileId(candidateValue, { trustedSource: true });
        }
      }
    }

    return "";
  }

  function getRowCollectionRoot() {
    return document.querySelector("#tableBody")
      || document.querySelector("tbody")
      || document.querySelector("[data-table-body]")
      || document.querySelector("[class*='table-body' i]")
      || document.querySelector("[class*='tbody' i]")
      || document.body;
  }

  function getCandidateRows(root) {
    var selectors = [
      "tr[data-id]",
      "tr",
      "[data-id][role='row']",
      "[role='row']",
      "[class*='table-row' i]",
      "[class*='row' i]"
    ];
    var rows = [];

    selectors.forEach(function (selector) {
      toArray(root.querySelectorAll(selector)).forEach(function (candidate) {
        if (rows.indexOf(candidate) === -1) {
          rows.push(candidate);
        }
      });
    });

    rows = rows.filter(function (candidate) {
      var cellCount = getRowCells(candidate).length;
      var hasControls = !!candidate.querySelector("input, select, textarea, [role='combobox']");
      return cellCount >= 2 || hasControls;
    });

    rows.sort(function (a, b) {
      if (a === b) {
        return 0;
      }
      return a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_PRECEDING ? 1 : -1;
    });

    return rows;
  }

  function extractRows(rowLimit) {
    var tableBody = getRowCollectionRoot();
    var headerMap = getTableHeaderMap(tableBody);
    var safeRowLimit = isPositiveNumber(rowLimit) ? rowLimit : 100;
    var rows;
    var unique = {};
    var results = [];
    var i;
    var row;
    var username;
    var model;
    var profileId;

    if (!tableBody) {
      return [];
    }

    rows = getCandidateRows(tableBody);

    if (!rows.length) {
      rows = toArray(tableBody.children).filter(function (candidate) {
        return candidate && (getRowCells(candidate).length > 0 || candidate.querySelector("input, select, textarea, [role='combobox']"));
      });
    }

    rows = rows.slice(0, safeRowLimit);

    for (i = 0; i < rows.length; i += 1) {
      row = rows[i];
      username = readUsername(row, headerMap);
      model = readSelectedModel(row, headerMap);
      profileId = readAdsPowerId(row, headerMap);

      if (!username || !profileId || unique[profileId]) {
        continue;
      }

      unique[profileId] = true;
      results.push({
        username: username,
        profile_id: profileId,
        model: model || "",
        source_rank: i,
      });
    }

    return results;
  }

  function extractDailyUpdateRows(rowLimit) {
    var tableBody = getRowCollectionRoot();
    var headerMap = getTableHeaderMap(tableBody);
    var safeRowLimit = isPositiveNumber(rowLimit) ? rowLimit : 100;
    var rows;
    var unique = {};
    var results = [];
    var i;
    var row;
    var username;
    var model;
    var profileId;

    if (!tableBody) {
      return [];
    }

    rows = getCandidateRows(tableBody);

    if (!rows.length) {
      rows = toArray(tableBody.children).filter(function (candidate) {
        return candidate && (getRowCells(candidate).length > 0 || candidate.querySelector("input, select, textarea, [role='combobox']"));
      });
    }

    rows = rows.slice(0, safeRowLimit);

    for (i = 0; i < rows.length; i += 1) {
      row = rows[i];
      username = readUsername(row, headerMap);
      model = readSelectedModel(row, headerMap);
      profileId = readAdsPowerId(row, headerMap);

      if (!profileId || unique[profileId]) {
        continue;
      }

      unique[profileId] = true;
      results.push({
        username: username || "",
        profile_id: profileId,
        model: model || "Unknown",
        source_rank: i,
      });
    }

    return results;
  }

  function ensureBitmojiIndicatorStyles() {
    var styleId = "nyx-bitmoji-indicator-styles";
    var style;

    if (document.getElementById(styleId)) {
      return;
    }

    style = document.createElement("style");
    style.id = styleId;
    // The indicator is absolutely positioned so it never adds layout width to
    // the username cell (the old inline dot pushed the text right and widened
    // the row). The row itself is marked by a status colour (left stripe + a
    // soft tint) so the whole row reads at a glance.
    style.textContent = [
      ".nyx-bitmoji-username-cell{position:relative !important;overflow:visible !important;}",
      ".nyx-bitmoji-row-indicator{position:absolute;left:3px;top:50%;transform:translateY(-50%);width:13px;height:13px;border-radius:999px;box-shadow:0 0 0 2px rgba(255,255,255,.9);cursor:pointer;z-index:5;}",
      ".nyx-bitmoji-row-indicator-has{background:#22c55e;}",
      ".nyx-bitmoji-row-indicator-missing{background:#ef4444;}",
      ".nyx-bitmoji-row-has{box-shadow:inset 4px 0 0 #22c55e !important;background:rgba(34,197,94,.10) !important;}",
      ".nyx-bitmoji-row-missing{box-shadow:inset 4px 0 0 #ef4444 !important;background:rgba(239,68,68,.10) !important;}",
      ".nyx-replace-menu{position:absolute;z-index:2147483647;background:#fff;border:1px solid #d0d7de;border-radius:8px;box-shadow:0 6px 20px rgba(15,39,71,.18);padding:4px;min-width:150px;}",
      ".nyx-replace-menu-item{display:block;width:100%;text-align:left;padding:8px 10px;font-size:13px;border:0;background:transparent;cursor:pointer;border-radius:6px;color:#b91c1c;font-weight:600;}",
      ".nyx-replace-menu-item:hover{background:#fef2f2;}",
      ".nyx-replace-outcome{position:absolute;right:6px;top:50%;transform:translateY(-50%);font-size:11px;font-weight:700;padding:2px 7px;border-radius:999px;white-space:nowrap;z-index:6;box-shadow:0 0 0 2px rgba(255,255,255,.9);}",
      ".nyx-replace-outcome-ok{background:#dcfce7;color:#166534;}",
      ".nyx-replace-outcome-fail{background:#fee2e2;color:#b91c1c;}"
    ].join("");
    document.head.appendChild(style);
  }

  function applyBitmojiIndicators(statuses) {
    var tableBody = getRowCollectionRoot();
    var headerMap = getTableHeaderMap(tableBody);
    var statusMap = {};
    var rows;
    var applied = 0;

    lastBitmojiStatuses = Array.isArray(statuses) ? statuses : [];
    ensureBitmojiIndicatorStyles();

    lastBitmojiStatuses.forEach(function (entry) {
      var profileId = normalizeProfileId(entry && entry.profile_id, { trustedSource: true });
      if (profileId) {
        statusMap[profileId] = {
          hasBitmoji: !!(entry && entry.has_bitmoji),
          username: normalizeText(entry && entry.username)
        };
      }
    });

    rows = getCandidateRows(tableBody);
    if (!rows.length) {
      rows = toArray(tableBody.children).filter(function (candidate) {
        return candidate && (getRowCells(candidate).length > 0 || candidate.querySelector("input, select, textarea, [role='combobox']"));
      });
    }

    rows.forEach(function (row) {
      var profileId = readAdsPowerId(row, headerMap);
      var status = statusMap[profileId];
      var usernameCell;
      var indicator;
      var indicators;
      var nextIndicatorClass;
      var nextTitle;

      if (!profileId || !status) {
        return;
      }

      usernameCell = getUsernameCell(row, headerMap);
      if (!usernameCell) {
        return;
      }
      usernameCell.classList.add("nyx-bitmoji-username-cell");

      row.classList.toggle("nyx-bitmoji-row-has", status.hasBitmoji);
      row.classList.toggle("nyx-bitmoji-row-missing", !status.hasBitmoji);

      indicators = toArray(usernameCell.querySelectorAll(".nyx-bitmoji-row-indicator"));
      indicator = indicators.find(function (candidate) {
        return candidate.getAttribute("data-nyx-profile-id") === profileId;
      });
      indicators.forEach(function (candidate) {
        if (candidate !== indicator) {
          candidate.remove();
        }
      });

      if (!indicator) {
        indicator = document.createElement("span");
        indicator.className = "nyx-bitmoji-row-indicator";
        indicator.setAttribute("title", "Bitmoji status — click for actions");
        indicator.addEventListener("click", function (event) {
          event.preventDefault();
          event.stopPropagation();
          var clickedRow = indicator.closest("tr");
          if (clickedRow) {
            openReplaceMenu(indicator, clickedRow);
          }
        });
        usernameCell.insertBefore(indicator, usernameCell.firstChild);
      }

      nextIndicatorClass = status.hasBitmoji
        ? "nyx-bitmoji-row-indicator nyx-bitmoji-row-indicator-has"
        : "nyx-bitmoji-row-indicator nyx-bitmoji-row-indicator-missing";
      nextTitle = status.hasBitmoji ? "Bitmoji done" : "No Bitmoji yet";
      if (indicator.className !== nextIndicatorClass) {
        indicator.className = nextIndicatorClass;
      }
      if (indicator.getAttribute("data-nyx-profile-id") !== profileId) {
        indicator.setAttribute("data-nyx-profile-id", profileId);
      }
      if (indicator.getAttribute("title") !== nextTitle) {
        indicator.setAttribute("title", nextTitle);
      }
      applied += 1;
    });

    return applied;
  }

  function clearBitmojiIndicators() {
    var rows = getCandidateRows(getRowCollectionRoot());
    var removed = 0;

    rows.forEach(function (row) {
      if (row.classList) {
        row.classList.remove("nyx-bitmoji-row-has");
        row.classList.remove("nyx-bitmoji-row-missing");
      }
    });

    toArray(document.querySelectorAll(".nyx-bitmoji-username-cell")).forEach(function (cell) {
      cell.classList.remove("nyx-bitmoji-username-cell");
    });

    toArray(document.querySelectorAll(".nyx-bitmoji-row-indicator")).forEach(function (indicator) {
      indicator.remove();
      removed += 1;
    });

    lastBitmojiStatuses = [];
    return removed;
  }

  function getRowLimit(callback) {
    try {
      if (
        typeof chrome === "undefined" ||
        !chrome ||
        !chrome.storage ||
        !chrome.storage.sync ||
        typeof chrome.storage.sync.get !== "function"
      ) {
        callback(100);
        return;
      }

      chrome.storage.sync.get(CONFIG_KEY, function (result) {
        var config = result && result[CONFIG_KEY] ? result[CONFIG_KEY] : {};
        var parsed = parseInt(config.rowLimit, 10);
        callback(isPositiveNumber(parsed) ? parsed : 100);
      });
    } catch (error) {
      callback(100);
    }
  }

  function sendRows() {
    getRowLimit(function (rowLimit) {
      var rows = extractRows(rowLimit);
      var normalizedRows;
      var signature;
      if (!rows.length) {
        lastSentSignature = "";
        return;
      }

      normalizedRows = rows.map(function (row) {
        return {
          username: row.username,
          profile_id: row.profile_id,
          model: row.model,
          source_rank: row.source_rank,
        };
      });
      signature = normalizedRows.map(function (row) {
        return row.profile_id + "|" + row.model;
      }).join("\n");

      if (signature === lastSentSignature) {
        return;
      }

      lastSentSignature = signature;
      chrome.runtime.sendMessage({
        type: "NYX_DETECTED_ROWS",
        rows: normalizedRows,
      });
    });
  }

  function queueScan() {
    window.clearTimeout(debounceTimer);
    debounceTimer = window.setTimeout(sendRows, 800);
  }

  function wait(ms) {
    return new Promise(function (resolve) {
      window.setTimeout(resolve, ms);
    });
  }

  function getInaccessibleStatusSelects() {
    return toArray(document.querySelectorAll("select.cell-select.status-select.status-inaccessible"))
      .filter(function (select) {
        return toArray(select.options || []).some(function (option) {
          return String(option.value || "").trim() === "Warm Up";
        });
      });
  }

  async function warmupAllInaccessible() {
    var selects = getInaccessibleStatusSelects();
    var updated = 0;
    var i;
    var select;

    for (i = 0; i < selects.length; i += 1) {
      select = selects[i];
      if (!select || String(select.value || "").trim() === "Warm Up") {
        continue;
      }

      select.value = "Warm Up";
      select.dispatchEvent(new Event("change", { bubbles: true }));
      updated += 1;
      await wait(180);
    }

    return updated;
  }

  // -------------------------------------------------------------------------
  // Replace Profile — dropdown action on the Bitmoji indicator. Refreshes the
  // proxy, sets the SnapBoard status to "Warm Up", clears the AdsPower ID on
  // SnapBoard (which makes Nyxify re-detect the row and re-queue it as PENDING),
  // and deletes the old AdsPower profile via the local Nyx runner. Reports the
  // outcome as an overlay badge inside the row.
  // -------------------------------------------------------------------------
  var REPLACE_MENU_ID = "nyx-replace-profile-menu";

  function clickNode(node) {
    if (!node) {
      return false;
    }
    try {
      if (typeof node.click === "function") {
        node.click();
        return true;
      }
    } catch (_error) {}
    try {
      node.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
      return true;
    } catch (_error2) {}
    return false;
  }

  function findRotateProxyButtonInRow(row) {
    if (!row) {
      return null;
    }
    var buttons = toArray(row.querySelectorAll("button, a[role='button'], [data-action]"));
    return buttons.find(function (button) {
      var text = normalizeText(button.innerText || button.textContent || "").toLowerCase();
      var title = normalizeText(button.getAttribute("title") || "").toLowerCase();
      var label = normalizeText(button.getAttribute("aria-label") || "").toLowerCase();
      var cls = normalizeText(button.className || "").toLowerCase();
      var onclickText = normalizeText(button.getAttribute("onclick") || "").toLowerCase();
      var hint = [text, title, label, cls, onclickText].join(" ");
      return hint.indexOf("rotateproxy") >= 0
        || hint.indexOf("rotate proxy") >= 0
        || hint.indexOf("new proxy") >= 0
        || hint.indexOf("refresh proxy") >= 0
        || (hint.indexOf("proxy") >= 0 && (hint.indexOf("refresh") >= 0 || hint.indexOf("reload") >= 0 || hint.indexOf("renew") >= 0 || hint.indexOf("rotate") >= 0));
    }) || null;
  }

  function setRowStatusWarmup(row) {
    if (!row) {
      return false;
    }
    var select = row.querySelector("select.cell-select.status-select")
      || row.querySelector("select.status-select")
      || toArray(row.querySelectorAll("select")).find(function (sel) {
        return toArray(sel.options || []).some(function (option) {
          return String(option.value || "").trim() === "Warm Up";
        });
      });
    if (!select) {
      return false;
    }
    var hasWarmUp = toArray(select.options || []).some(function (option) {
      return String(option.value || "").trim() === "Warm Up";
    });
    if (!hasWarmUp) {
      return false;
    }
    if (String(select.value || "").trim() === "Warm Up") {
      return true;
    }
    select.value = "Warm Up";
    select.dispatchEvent(new Event("change", { bubbles: true }));
    return String(select.value || "").trim() === "Warm Up";
  }

  // Content scripts run in an isolated world and cannot call SnapBoard's page
  // function updateField(...). Injecting a <script> runs in the page world.
  function callPageUpdateField(rowId, field, value) {
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
          "}" +
        "}catch(_e){}}" +
        "applyValue();" +
        "if(typeof updateField==='function'){try{updateField(rid,field,value);}catch(_u){}}" +
        "setTimeout(applyValue,120);setTimeout(applyValue,400);" +
        "}catch(e){}})();";
      (document.head || document.documentElement).appendChild(script);
      script.remove();
      return true;
    } catch (_error) {
      return false;
    }
  }

  function clearAdspowerIdInRow(row, rowId) {
    if (!row) {
      return false;
    }
    var input = row.querySelector("input.cell-input.input-adspower")
      || row.querySelector("input.input-adspower")
      || row.querySelector("input[onchange*=\"adspowerId\"]");
    if (input) {
      try {
        var proto = input.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        var desc = Object.getOwnPropertyDescriptor(proto, "value");
        if (desc && desc.set) {
          desc.set.call(input, "");
        } else {
          input.value = "";
        }
      } catch (_error) {
        input.value = "";
      }
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }
    if (rowId) {
      callPageUpdateField(rowId, "adspowerId", "");
    }
    return true;
  }

  function showRowOutcome(row, ok, text) {
    var cell = getUsernameCell(row, getTableHeaderMap(getRowCollectionRoot())) || row;
    if (!cell || !cell.classList) {
      return;
    }
    cell.classList.add("nyx-bitmoji-username-cell");
    var existing = cell.querySelector(".nyx-replace-outcome");
    if (existing) {
      existing.remove();
    }
    var badge = document.createElement("span");
    badge.className = "nyx-replace-outcome " + (ok ? "nyx-replace-outcome-ok" : "nyx-replace-outcome-fail");
    badge.textContent = (ok ? "✓ " : "✗ ") + String(text || (ok ? "Replaced" : "Failed"));
    badge.title = badge.textContent;
    cell.appendChild(badge);
    window.setTimeout(function () {
      if (badge && badge.parentNode) {
        badge.remove();
      }
    }, ok ? 6000 : 12000);
  }

  function closeReplaceMenu() {
    var menu = document.getElementById(REPLACE_MENU_ID);
    if (menu) {
      menu.remove();
    }
    document.removeEventListener("click", onDocumentClickForMenu, true);
  }

  function onDocumentClickForMenu(event) {
    var menu = document.getElementById(REPLACE_MENU_ID);
    var onIndicator = event.target && event.target.classList && event.target.classList.contains("nyx-bitmoji-row-indicator");
    if (menu && !menu.contains(event.target) && !onIndicator) {
      closeReplaceMenu();
    }
  }

  function openReplaceMenu(indicator, row) {
    closeReplaceMenu();
    var menu = document.createElement("div");
    menu.id = REPLACE_MENU_ID;
    menu.className = "nyx-replace-menu";
    var item = document.createElement("button");
    item.type = "button";
    item.className = "nyx-replace-menu-item";
    item.textContent = "Replace profile";
    item.addEventListener("click", function (event) {
      event.stopPropagation();
      closeReplaceMenu();
      var ok = window.confirm(
        "Replace this profile?\n\nThis refreshes the proxy, sets the status to Warm Up, "
        + "clears the AdsPower ID on SnapBoard, deletes the AdsPower profile, and re-queues "
        + "the row in Nyxify."
      );
      if (ok) {
        replaceProfileForRow(row);
      }
    });
    menu.appendChild(item);
    document.body.appendChild(menu);
    var rect = indicator.getBoundingClientRect();
    menu.style.top = (window.scrollY + rect.bottom + 4) + "px";
    menu.style.left = (window.scrollX + rect.left) + "px";
    window.setTimeout(function () {
      document.addEventListener("click", onDocumentClickForMenu, true);
    }, 0);
  }

  function replaceProfileForRow(row) {
    var headerMap = getTableHeaderMap(getRowCollectionRoot());
    var rowId = row.getAttribute("data-id") || "";
    var adspowerId = readAdsPowerId(row, headerMap);
    var reasons = [];

    showRowOutcome(row, true, "Replacing…");

    // 1) Refresh the proxy for this row.
    var proxyButton = findRotateProxyButtonInRow(row);
    if (proxyButton) {
      clickNode(proxyButton);
    } else {
      reasons.push("proxy button not found");
    }

    // 2) Set the SnapBoard status to "Warm Up".
    if (!setRowStatusWarmup(row)) {
      reasons.push("could not set Warm Up status");
    }

    // 3) Clear the AdsPower ID on SnapBoard. Nyxify only queues rows with no
    //    AdsPower ID, so clearing it makes Nyxify re-detect and re-queue this
    //    row as PENDING (the "move to pending in nyxify" step).
    clearAdspowerIdInRow(row, rowId);

    // 4) Delete the old AdsPower profile via the local Nyx runner.
    if (!adspowerId) {
      showRowOutcome(row, false, "no AdsPower ID" + (reasons.length ? "; " + reasons.join("; ") : ""));
      return;
    }
    chrome.runtime.sendMessage({ type: "NYX_DELETE_ADSPOWER_PROFILE", profileId: adspowerId }, function (response) {
      if (chrome.runtime.lastError) {
        showRowOutcome(row, false, "runner unreachable" + (reasons.length ? "; " + reasons.join("; ") : ""));
        return;
      }
      if (!response || !response.ok) {
        var error = (response && response.error) ? response.error : "delete failed";
        showRowOutcome(row, false, error + (reasons.length ? "; " + reasons.join("; ") : ""));
        return;
      }
      if (reasons.length) {
        showRowOutcome(row, false, "partial — " + reasons.join("; "));
      } else {
        showRowOutcome(row, true, "Replaced");
      }
    });
  }

  function onDomReady() {
    document.removeEventListener("DOMContentLoaded", onDomReady);
    queueScan();
  }

  function isRelevantMutation(mutation) {
    var target = mutation && mutation.target;
    var addedNodes = toArray(mutation && mutation.addedNodes);
    var removedNodes = toArray(mutation && mutation.removedNodes);
    var relevantText = "tableBody tbody input-adspower input-username cell-select status-select";

    function isRelevantNode(node) {
      if (!node || node.nodeType !== 1) {
        return false;
      }

      if (node.matches && node.matches("tr, td, th, tbody, table, input, select, textarea, [role='row'], [data-id]")) {
        return true;
      }

      return typeof node.querySelector === "function" && !!node.querySelector("tr, td, th, tbody, table, input, select, textarea, [role='row'], [data-id]");
    }

    if (target && target.nodeType === 1) {
      if (isRelevantNode(target)) {
        return true;
      }
      if (String(target.className || "").toLowerCase().indexOf("row") !== -1) {
        return true;
      }
      if (String(target.id || "").toLowerCase().indexOf("table") !== -1) {
        return true;
      }
      if (relevantText.indexOf(String(target.className || "").toLowerCase()) !== -1) {
        return true;
      }
    }

    return addedNodes.some(isRelevantNode) || removedNodes.some(isRelevantNode);
  }

  var observer = new MutationObserver(function (mutations) {
    if ((mutations || []).some(isRelevantMutation)) {
      queueScan();
      if (lastBitmojiStatuses.length) {
        window.setTimeout(function () {
          applyBitmojiIndicators(lastBitmojiStatuses);
        }, 120);
      }
    }
  });
  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", onDomReady);
  } else {
    queueScan();
  }

  if (typeof chrome !== "undefined" && chrome && chrome.runtime && typeof chrome.runtime.onMessage !== "undefined") {
    chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
      if (message && message.type === "NYX_GET_RENAME_ROWS") {
        getRowLimit(function (rowLimit) {
          var requestedCount = parseInt(message.count, 10);
          var safeLimit = isPositiveNumber(requestedCount) ? Math.max(rowLimit, requestedCount) : rowLimit;
          var rows = extractRows(safeLimit);
          sendResponse({ ok: true, rows: rows });
        });

        return true;
      }

      if (message && message.type === "NYX_GET_DAILY_UPDATE_ROWS") {
        getRowLimit(function (rowLimit) {
          var requestedCount = parseInt(message.count, 10);
          var safeLimit = isPositiveNumber(requestedCount) ? Math.max(rowLimit, requestedCount) : rowLimit;
          var rows = extractDailyUpdateRows(safeLimit);
          sendResponse({ ok: true, rows: rows });
        });

        return true;
      }

      if (message && message.type === "NYX_SHOW_BITMOJI_INDICATORS") {
        sendResponse({
          ok: true,
          count: applyBitmojiIndicators(message.statuses || [])
        });
        return true;
      }

      if (message && message.type === "NYX_HIDE_BITMOJI_INDICATORS") {
        sendResponse({
          ok: true,
          count: clearBitmojiIndicators()
        });
        return true;
      }

      if (message && message.type === "NYX_GET_BITMOJI_INDICATOR_STATE") {
        sendResponse({
          ok: true,
          visible: lastBitmojiStatuses.length > 0
        });
        return true;
      }

      if (!message || message.type !== "NYX_WARMUP_ALL_INACCESSIBLE") {
        return;
      }

      warmupAllInaccessible()
        .then(function (updated) {
          sendResponse({ ok: true, updated: updated });
        })
        .catch(function (error) {
          sendResponse({ ok: false, error: error && error.message ? error.message : "Warm Up All failed." });
        });

      return true;
    });
  }

  window.setInterval(queueScan, 15000);
})();
