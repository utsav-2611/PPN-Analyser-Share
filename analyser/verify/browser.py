"""Headless Chromium for official sites that are single-page apps (CRS, NDMC).

render(url, ready_pattern) -> (text, error): a fresh browser context per page (so an app cannot show the previous record),
TLS checking on, waits until the page text matches `ready_pattern` (or SETTLE_MS passes), returns the visible text.
Errors are returned as a short code (exception type and network error name); the message is cut so it cannot echo the URL.
"""
import os
import re
import time

TIMEOUT_MS = 45_000
SETTLE_MS = 20_000
_last = {}
BLOCKED = set()   # non government hosts the page asked for in the last render (names of sites only, never URLs)


def allowed_request(url):
    """Only government sites (and inline data) may be contacted: anything else would receive the certificate link as a referrer."""
    from .. import qr
    from urllib.parse import urlparse
    if url.startswith(("data:", "blob:", "about:")):
        return True
    host = urlparse(url).hostname or ""
    return qr.is_government_host(host)


def error_code(e):
    msg = str(e).splitlines()[0] if str(e) else ""
    net = re.search(r"net::ERR_[A-Z0-9_]+", msg)
    if net:
        return f"{type(e).__name__} {net.group(0)}"
    return f"{type(e).__name__} {re.sub(r'https?://\S+', '<url>', msg)[:80]}".strip()


def render(url, ready_pattern, capture=None, gap_key="default", min_gap=3.0, timeout_ms=TIMEOUT_MS, wait_until="domcontentloaded"):
    """`capture`, if a list, receives (method, url shape, json keys) for JSON XHR/fetch responses."""
    if os.environ.get("PPN_CACHE_ONLY"):  # diagnostics: never open a page that is not already cached
        return "", "not cached"
    from playwright.sync_api import TimeoutError as PWTimeout
    from playwright.sync_api import sync_playwright

    wait = min_gap - (time.time() - _last.get(gap_key, 0))
    if wait > 0:
        time.sleep(wait)
    _last[gap_key] = time.time()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                page = browser.new_context(locale="en-IN").new_page()
                BLOCKED.clear()

                def gate(route):
                    if allowed_request(route.request.url):
                        route.continue_()
                    else:
                        BLOCKED.add(re.sub(r"^[a-z]+://([^/:]+).*$", r"\1", route.request.url))
                        route.abort()
                page.route("**/*", gate)
                if capture is not None:
                    def on_response(resp):
                        try:
                            if resp.request.resource_type in ("xhr", "fetch") and "json" in (resp.headers.get("content-type") or ""):
                                body = resp.json()
                                keys = sorted(body)[:25] if isinstance(body, dict) else f"list of {len(body)}"
                                u = re.sub(r"\?.*", "?...", resp.url)
                                capture.append((resp.request.method, re.sub(r"[A-Za-z0-9+/=_%-]{20,}", "<id>", u), keys))
                        except Exception:
                            pass
                    page.on("response", on_response)
                page.goto(url, wait_until=wait_until, timeout=timeout_ms)
                try:
                    page.wait_for_function("(p) => !!document.body && new RegExp(p, 'i').test(document.body.innerText)", arg=ready_pattern, timeout=SETTLE_MS)
                except PWTimeout:
                    pass
                text = page.inner_text("body")
                final = re.sub(r"[A-Za-z0-9+/=_%-]{20,}", "<id>", page.url)
            finally:
                browser.close()
    except Exception as e:
        return "", error_code(e)
    if capture is not None:
        capture.append(("FINAL", final, ""))
    return text, ""
