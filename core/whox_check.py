"""whox.com trust-score gate for Nyxify profile creation.

Runs right after an AdsPower profile opens (before cookie warm-up): navigate to
whox.com, run its Deep Scan, and read the resulting Deep Trust Score. The runner
uses that score to decide whether to keep the profile (score >= threshold) or
close+delete it and recreate the row from scratch (score below threshold).

The DOM contract was captured live against whox.com:

  * ``.deep-scan-btn``   — the "Run Deep Scan" button.
  * ``.score-orb``       — carries ``data-has-results``, ``data-scanning`` and
                           ``data-complete`` attributes that drive the flow.
  * ``.score-orb-number``— the score. While scanning it shows a progress "N%";
                           once settled it is the plain integer trust score.
  * ``.score-orb-name``  — "Fast Trust Score" before the deep scan,
                           "Deep Trust Score" during/after it.

A deep scan takes ~13-20s on a clean IP and can run longer over a slow proxy, so
the waits are generous and env-tunable. This module never raises for a browser
hiccup — it returns a structured result and lets the runner decide.
"""

import asyncio
import os


def _env_int(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return int(default)


def _env_bool(name, default):
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() not in {"0", "false", "no", "off"}


DEFAULT_WHOX_URL = os.getenv("NYXIFY_WHOX_URL", "https://whox.com/").strip() or "https://whox.com/"
# Seconds to wait for the initial page + Fast Trust Score to settle before the
# deep scan is triggered. Clicking too early yields a degenerate score.
WHOX_SETTLE_TIMEOUT = max(5, _env_int("NYXIFY_WHOX_SETTLE_TIMEOUT", 30))
# Seconds to wait for the deep scan itself to finish (progress 0% -> 100% ->
# settled score). Generous so a slow proxy still resolves.
WHOX_DEEP_SCAN_TIMEOUT = max(20, _env_int("NYXIFY_WHOX_DEEP_SCAN_TIMEOUT", 120))
WHOX_NAV_TIMEOUT_MS = max(10000, _env_int("NYXIFY_WHOX_NAV_TIMEOUT_MS", 60000))
# When the check cannot produce a score (whox unreachable, layout changed, timed
# out), continue to signup instead of destroying the profile. This is opt-out.
WHOX_FAIL_OPEN = _env_bool("NYXIFY_WHOX_FAIL_OPEN", True)

# Single in-page orchestration: settle the fast score, click Deep Scan, wait for
# completion, return the integer score. Mirrors the flow validated live so the
# selector/attribute contract lives in one place.
_WHOX_EVAL_JS = r"""
async ({ settleMs, deepMs }) => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const q = (s) => document.querySelector(s);
  const readNumber = () => {
    const el = q('.score-orb-number');
    if (!el) return { present: false };
    const text = (el.textContent || '').trim();
    if (text.includes('%')) return { present: true, scanning: true, raw: text };
    const n = parseInt(text, 10);
    return { present: true, scanning: false, raw: text, value: Number.isNaN(n) ? null : n };
  };
  const orbAttr = (name) => {
    const orb = q('.score-orb');
    return orb ? orb.getAttribute(name) : null;
  };

  // 1) Wait for the deep-scan button to exist.
  const s0 = Date.now();
  while (Date.now() - s0 < settleMs * 1000) {
    if (q('.deep-scan-btn')) break;
    await sleep(150);
  }
  if (!q('.deep-scan-btn')) {
    return { ok: false, stage: 'no_button', reason: 'Deep Scan button never appeared' };
  }

  // 2) Wait for the Fast Trust Score to settle: results present, not scanning,
  //    and a plain numeric score stable for ~1.2s.
  let stableVal = null, stableSince = 0, settled = false;
  const s1 = Date.now();
  while (Date.now() - s1 < settleMs * 1000) {
    const num = readNumber();
    const hasResults = orbAttr('data-has-results') === 'true';
    const scanning = orbAttr('data-scanning') === 'true';
    if (hasResults && !scanning && num.present && !num.scanning && num.value !== null) {
      if (num.value === stableVal) {
        if (Date.now() - stableSince >= 1200) { settled = true; break; }
      } else {
        stableVal = num.value;
        stableSince = Date.now();
      }
    }
    await sleep(150);
  }
  const fast = readNumber();
  if (!settled) {
    // The page never produced a stable Fast Trust Score (whox didn't finish
    // loading / results never resolved). Clicking Deep Scan here yields a
    // degenerate score, so report inconclusive instead of risking a false FAIL.
    return {
      ok: false,
      stage: 'fast_score_unsettled',
      reason: 'Fast Trust Score never settled',
      fastScore: fast.value ?? null,
    };
  }

  // 3) Trigger the deep scan.
  const btn = q('.deep-scan-btn');
  if (!btn) return { ok: false, stage: 'button_lost', reason: 'Deep Scan button disappeared' };
  try { btn.click(); } catch (e) {
    return { ok: false, stage: 'click_failed', reason: String(e) };
  }

  // 4) Wait for the scan to complete, THEN wait for the score to settle. whox
  //    flips data-complete=true and *then* animates the number from ~0 up to the
  //    final deep score over ~1-2s, so reading at data-complete=true catches a
  //    transient animation frame (observed live: 78 -> 0 -> 5 -> ... -> 76).
  //    Only a value that holds steady for STABLE_MS is the real score.
  const STABLE_MS = 1500;
  const s2 = Date.now();
  let completed = false;
  let dStableVal = null, dStableSince = 0, deepValue = null;
  while (Date.now() - s2 < deepMs * 1000) {
    const num = readNumber();
    const complete = orbAttr('data-complete') === 'true';
    const scanning = orbAttr('data-scanning') === 'true';
    if (complete && !scanning && num.present && !num.scanning && num.value !== null) {
      if (num.value === dStableVal) {
        if (Date.now() - dStableSince >= STABLE_MS) { completed = true; deepValue = num.value; break; }
      } else {
        dStableVal = num.value;
        dStableSince = Date.now();
      }
    } else {
      // Reset while still scanning / animating percentage.
      dStableVal = null;
      dStableSince = 0;
    }
    await sleep(200);
  }
  const deep = { present: true, scanning: false, raw: String(deepValue), value: deepValue };
  const name = q('.score-orb-name');
  const issues = q('.score-orb-issues');

  if (!completed || deep.value === null) {
    return {
      ok: false,
      stage: 'scan_timeout',
      reason: 'Deep scan did not settle to a numeric score',
      fastScore: fast.value ?? null,
      scoreName: name ? (name.textContent || '').trim() : null,
      fastSettled: settled,
    };
  }
  return {
    ok: true,
    score: deep.value,
    fastScore: fast.value ?? null,
    scoreName: name ? (name.textContent || '').trim() : null,
    tone: orbAttr('data-tone'),
    issues: issues ? (issues.getAttribute('aria-label') || issues.textContent || '').trim() : null,
    fastSettled: settled,
  };
}
"""


async def _safe_close_page(page):
    if page is None:
        return
    try:
        await page.close()
    except Exception:
        pass


async def run_whox_trust_check(
    context,
    logger,
    profile_id,
    min_score,
    whox_url=None,
    settle_timeout=None,
    deep_scan_timeout=None,
):
    """Open whox.com, run the deep scan, and evaluate the trust score.

    Returns a dict:
      {
        "ran": bool,           # the scan produced a score
        "score": int | None,   # deep trust score
        "threshold": int,
        "passed": bool,        # keep the profile? (score >= threshold, or
                               #  fail-open when the scan was inconclusive)
        "error": str,          # populated when the scan could not complete
        "detail": dict,        # raw in-page result for logging
      }
    """
    threshold = int(min_score)
    url = str(whox_url or DEFAULT_WHOX_URL).strip() or DEFAULT_WHOX_URL
    settle = int(settle_timeout or WHOX_SETTLE_TIMEOUT)
    deep = int(deep_scan_timeout or WHOX_DEEP_SCAN_TIMEOUT)
    # Overall Python-side guard: in-page deadline + navigation + slack.
    overall_timeout = settle + deep + 45

    def _inconclusive(error, detail=None):
        # Fail-open by default: an unreadable whox result should not destroy a
        # profile. The runner still has its own downstream signup retries.
        return {
            "ran": False,
            "score": None,
            "threshold": threshold,
            "passed": bool(WHOX_FAIL_OPEN),
            "error": str(error or "whox check inconclusive"),
            "detail": detail or {},
        }

    page = None
    try:
        try:
            page = await context.new_page()
        except Exception as exc:
            # Never let a browser/context failure crash the pipeline: a
            # profile-destroying gate that itself throws would be worse than
            # skipping it. Fail-open.
            if logger:
                logger.warning(f"whox check for {profile_id}: could not open a page: {exc}")
            return _inconclusive(f"whox page open failed: {exc}")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=WHOX_NAV_TIMEOUT_MS)
        except Exception as exc:
            if logger:
                logger.warning(f"whox check for {profile_id}: could not open {url}: {exc}")
            return _inconclusive(f"whox navigation failed: {exc}")

        if logger:
            logger.info(
                f"whox check for {profile_id}: running deep scan on {url} "
                f"(threshold={threshold})."
            )

        try:
            result = await asyncio.wait_for(
                page.evaluate(_WHOX_EVAL_JS, {"settleMs": settle, "deepMs": deep}),
                timeout=overall_timeout,
            )
        except asyncio.TimeoutError:
            if logger:
                logger.warning(
                    f"whox check for {profile_id}: deep scan exceeded {overall_timeout}s; "
                    f"treating as {'pass' if WHOX_FAIL_OPEN else 'fail'} (fail-open={WHOX_FAIL_OPEN})."
                )
            return _inconclusive("whox deep scan timed out")
        except Exception as exc:
            if logger:
                logger.warning(f"whox check for {profile_id}: evaluate failed: {exc}")
            return _inconclusive(f"whox evaluate failed: {exc}")

        if not isinstance(result, dict) or not result.get("ok"):
            reason = (result or {}).get("reason") if isinstance(result, dict) else "unknown"
            if logger:
                logger.warning(
                    f"whox check for {profile_id}: inconclusive ({reason}); "
                    f"fail-open={WHOX_FAIL_OPEN}. detail={result}"
                )
            return _inconclusive(f"whox scan inconclusive: {reason}", result if isinstance(result, dict) else None)

        try:
            score = int(result.get("score"))
        except (TypeError, ValueError):
            return _inconclusive("whox returned a non-numeric score", result)
        passed = score >= threshold
        if logger:
            logger.info(
                f"whox check for {profile_id}: deep trust score {score} "
                f"(threshold {threshold}) -> {'PASS' if passed else 'FAIL'}; "
                f"fast={result.get('fastScore')} tone={result.get('tone')} "
                f"issues={result.get('issues')}"
            )
        return {
            "ran": True,
            "score": score,
            "threshold": threshold,
            "passed": passed,
            "error": "",
            "detail": result,
        }
    finally:
        await _safe_close_page(page)
