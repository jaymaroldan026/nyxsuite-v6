(function () {
  var sent = false;
  var pollIntervalId = null;
  var fallbackTimeoutId = null;
  var observer = null;
  var detectorTimeoutMs = 12000;

  function toArray(nodeList) {
    return Array.prototype.slice.call(nodeList || []);
  }

  function normalizeText(value) {
    return String(value || "").trim();
  }

  function getUsernameFromPath() {
    var match = window.location.pathname.match(/^\/@([^/?#]+)/);
    return match ? normalizeText(match[1]) : "";
  }

  function detectProfileState() {
    var pageText = normalizeText(document.body ? document.body.innerText : "");
    var bitmojiImageByPattern = toArray(document.querySelectorAll("img")).find(function (img) {
      var src = normalizeText(img.getAttribute("src") || "");
      var srcset = normalizeText(img.getAttribute("srcset") || "");
      var dataSrc = normalizeText(img.getAttribute("data-src") || "");
      var alt = normalizeText(img.getAttribute("alt") || "");
      var className = normalizeText(img.className || "");
      var combined = [src, srcset, dataSrc, alt, className].join(" ").toLowerCase();
      return combined.indexOf("/3d/render/") !== -1
        || combined.indexOf("3d bitmoji") !== -1
        || combined.indexOf("bitmoji3dimage") !== -1;
    });
    var bitmojiImage = document.querySelector(
      [
        ".Bitmoji3DImage_webPImageWrapper__u_akx img",
        "picture.Bitmoji3DImage_webPImage__g9_r2 img",
        "img.Bitmoji3DImage_webPImage__g9_r2",
        "img[class*='Bitmoji3DImage_webPImage' i]",
        "picture[class*='Bitmoji3DImage_webPImage' i] img",
        "img[alt^='3D Bitmoji for' i]",
        "img[alt*='3D Bitmoji' i]",
        "img[srcset*='cf-st.sc-cdn.net/3d/render']",
        "img[src*='cf-st.sc-cdn.net/3d/render']",
        "img[data-src*='cf-st.sc-cdn.net/3d/render']",
        "img[src*='/3d/render/']",
        "img[srcset*='/3d/render/']",
        "img[data-src*='/3d/render/']"
      ].join(", ")
    );
    var snapcodeImage = document.querySelector("img[data-testid='snapCodeImage'], img[src*='deeplink/snapcode']");
    var noContent = document.querySelector(".NoContent_columnItem__9Q3Kc");

    if (bitmojiImage || bitmojiImageByPattern) {
      return {
        has_bitmoji: true,
        evidence: bitmojiImage ? "bitmoji-image" : "bitmoji-image-pattern",
        status: "has_bitmoji",
      };
    }

    if (noContent || /this content was not found/i.test(pageText)) {
      return {
        has_bitmoji: false,
        evidence: "content-not-found",
        status: "not_found",
      };
    }

    if (snapcodeImage) {
      return {
        has_bitmoji: false,
        evidence: "snapcode-only",
        status: "no_bitmoji",
      };
    }

    return {
      has_bitmoji: false,
      evidence: "unknown-layout",
      status: "unknown",
    };
  }

  function stopWatchers() {
    if (pollIntervalId) {
      window.clearInterval(pollIntervalId);
      pollIntervalId = null;
    }
    if (fallbackTimeoutId) {
      window.clearTimeout(fallbackTimeoutId);
      fallbackTimeoutId = null;
    }
    if (observer) {
      observer.disconnect();
      observer = null;
    }
  }

  function sendResult(forceUnknown) {
    var username = getUsernameFromPath();
    var detected;
    if (!username || sent) {
      return;
    }

    detected = detectProfileState();
    if (!forceUnknown && detected.status === "unknown") {
      return;
    }

    sent = true;
    stopWatchers();

    chrome.runtime.sendMessage({
      type: "NYX_SCRAPE_SNAPCHAT_RESULT",
      payload: {
        username: username,
        profile_url: window.location.href,
        has_bitmoji: detected.has_bitmoji,
        evidence: detected.evidence,
        status: detected.status,
      },
    });
  }

  function queueCheck() {
    sendResult(false);
  }

  function scheduleWatchers() {
    observer = new MutationObserver(queueCheck);
    observer.observe(document.documentElement, {
      childList: true,
      subtree: true,
      attributes: true,
    });

    pollIntervalId = window.setInterval(queueCheck, 250);
    fallbackTimeoutId = window.setTimeout(function () {
      sendResult(true);
    }, detectorTimeoutMs);
  }

  try {
    if (typeof chrome !== "undefined" && chrome && chrome.storage && chrome.storage.sync) {
      chrome.storage.sync.get("nyxScrapeConfig", function (data) {
        var config = data && data.nyxScrapeConfig ? data.nyxScrapeConfig : {};
        var configuredTimeout = parseInt(config.profileTimeoutMs, 10);

        if (isFinite(configuredTimeout) && configuredTimeout > 4000) {
          detectorTimeoutMs = Math.max(9000, configuredTimeout - 1500);
        }

        scheduleWatchers();
        queueCheck();
      });
    } else {
      scheduleWatchers();
      queueCheck();
    }
  } catch (error) {
    scheduleWatchers();
    queueCheck();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", queueCheck, { once: true });
  } else {
    queueCheck();
  }
})();
