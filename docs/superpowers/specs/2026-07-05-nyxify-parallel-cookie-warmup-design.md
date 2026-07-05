# Nyxify Parallel Cookie Warmup Design

## Goal

Make Nyxify cookie warmup faster by visiting the selected warmup sites in capped parallel tabs, while keeping the browser clean before Snapchat signup opens.

## Current Flow

`nyxify_runner.py` disables AdsPower profile extensions, calls `warm_ads_profile_cookies(...)`, waits for it to finish, then calls `open_snapchat_signup(...)`.

`core/adspower_extension_cleanup.py` currently selects 5-10 warmup sites and visits them sequentially. Each site page already performs the desired warmup behavior: cookie consent acceptance, random scrolls, occasional same-origin clicks, and page cleanup.

## Approved Approach

Use capped parallel warmup:

- Continue selecting `NYXIFY_COOKIE_WARMUP_MIN_SITES` to `NYXIFY_COOKIE_WARMUP_MAX_SITES` random sites.
- Add `NYXIFY_COOKIE_WARMUP_MAX_CONCURRENT_TABS`, defaulting to `4`.
- Run selected sites concurrently through an `asyncio.Semaphore`.
- Preserve existing per-site behavior inside `_warm_one_cookie_site`.
- Snapshot pages before warmup starts.
- In a `finally` block, close every page that was created after the baseline snapshot.
- Return only successful warmup visits in `visited`.
- Let `nyxify_runner.py` proceed to Snapchat only after warmup cleanup completes.

## Error Handling

One failed warmup site should not stop the rest of the warmup batch. Exceptions from a site worker should be logged and treated as a failed visit.

Warmup cleanup must run even if a page fails navigation, a random interaction errors, or a worker raises unexpectedly.

## Configuration

New optional environment variable:

```text
NYXIFY_COOKIE_WARMUP_MAX_CONCURRENT_TABS=4
```

Values below `1` are clamped to `1`. The effective cap is also limited to the number of selected warmup sites.

## Testing

Add focused unit tests in `tests/test_nyxify_cookie_warmup.py`:

- Warmup honors the configured concurrency cap.
- Warmup closes all pages opened after the baseline page snapshot before returning.
- A failed site worker does not prevent other selected sites from completing.
- Existing Snapchat signup helper behavior remains unchanged.
