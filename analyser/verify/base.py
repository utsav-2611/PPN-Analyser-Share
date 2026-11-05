"""Common pieces for the official-site verifiers: Record, polite cached fetch."""
import hashlib
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

CACHE = Path(__file__).resolve().parent.parent.parent / "store" / "cache" / "verify"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
TIMEOUT = 30
_last_call = 0.0


@dataclass
class Record:
    """What an official site showed for one certificate."""
    source: str                    # e.g. "ulb", "edisha"
    status: str = "failed"         # verified | failed | na
    text: str = ""                 # full extracted text (stays local)
    fields: dict = field(default_factory=dict)   # parsed key facts
    error: str = ""                # short reason when not verified; no personal data


def _government(host):
    from .. import qr
    return qr.is_government_host(host)


def _key(url):
    return hashlib.sha256(url.encode()).hexdigest()


def fetch(url, retries=3, min_gap=1.0, use_cache=True):
    """GET url, return (bytes | None, error). Sequential and cached by URL hash."""
    global _last_call
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{_key(url)}.bin"
    if use_cache and f.exists():
        return f.read_bytes(), ""
    err = ""
    for attempt in range(retries):
        wait = min_gap - (time.time() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.time()
        # System curl verifies certificates with the macOS keychain; Python's urllib cannot complete
        # the incomplete chain some government sites send. Verification stays on.
        tmp = f.with_suffix(f".{os.getpid()}.dl")  # per process: parallel runs may fetch the same URL
        try:
            done = subprocess.run(
                ["/usr/bin/curl", "-sS", "-L", "--max-redirs", "5", "--proto", "=http,https", "--proto-redir", "=http,https",
                 "--fail", "-m", str(TIMEOUT), "-A", UA, "-o", str(tmp), "-w", "%{url_effective}", url],
                capture_output=True, timeout=TIMEOUT + 10)
        except Exception as e:
            err = type(e).__name__
        else:
            final_host = urlparse(done.stdout.decode("utf-8", "replace").strip()).hostname or ""
            if done.returncode == 0 and tmp.exists() and tmp.stat().st_size:
                if not _government(final_host):
                    tmp.unlink(missing_ok=True)
                    return None, "redirected to a non government site"  # never keep or read what another site sent
                tmp.replace(f)
                return f.read_bytes(), ""
            err = f"curl exit {done.returncode}"  # message omitted: it may echo the URL
        tmp.unlink(missing_ok=True)
        time.sleep(2 * (attempt + 1))
    return None, err
