"""Local store: store/results.json holds the analysed requests (one record each, with the recommendation and remark).

Writes are atomic (temp file + rename) and read-modify-write cycles run under a file lock.
"""
import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORE_DIR = Path(os.environ.get("PPN_STORE_DIR", ROOT / "store"))
RESULTS = STORE_DIR / "results.json"


def lock_down(path=None):
    """Owner-only access to the store and its caches (they hold certificate and decree text)."""
    root = Path(path or STORE_DIR)
    if not root.exists():
        return
    os.chmod(root, 0o700)
    for p in root.rglob("*"):
        try:
            os.chmod(p, 0o700 if p.is_dir() else 0o600)
        except OSError:
            pass


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _empty():
    return {"version": 1, "requests": {}}


def read(path=None):
    path = Path(path or RESULTS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _empty()
    data.setdefault("requests", {})
    return data


def write(data, path=None):
    path = Path(path or RESULTS)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".results-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


@contextmanager
def locked(path=None):
    """Yield the store data; it is written back when the block ends without an error."""
    path = Path(path or RESULTS)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.parent / ".results.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = read(path)
        yield data
        write(data, path)


# ---- analyser side ---------------------------------------------------------------------------
def merge_requests(data, records):
    """Add new requests; replace the record of a request analysed again.  Returns counts."""
    counts = {"new": 0, "refreshed": 0}
    for rec in records:
        counts["refreshed" if rec["id"] in data["requests"] else "new"] += 1
        data["requests"][rec["id"]] = rec
    return counts
