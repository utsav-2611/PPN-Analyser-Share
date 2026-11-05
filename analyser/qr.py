"""Render certificate PDFs and decode QR codes.

Run as a report:  python -m analyser.qr [marital|marriage|dob ...]
The report prints hit rates and host categories only, never QR text or ids.
"""
import csv
import hashlib
import io
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import cv2
import numpy as np
import pypdf
import pypdfium2 as pdfium
import yaml
from PIL import Image

from . import load

try:  # OpenCV prints harmless 'ECI is not supported' warnings
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
except Exception:
    pass

CACHE = Path(__file__).resolve().parent.parent / "store" / "cache" / "qr"

# Homebrew on Apple Silicon is not on the default library path; pyzbar looks it up at import.
os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = "/opt/homebrew/lib:" + os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")

try:  # optional second decoder (needs: brew install zbar)
    from pyzbar import pyzbar
    from pyzbar.pyzbar import ZBarSymbol
except Exception:
    pyzbar = None

DPIS = (220, 300)
MAX_PAGES = 8
DEFAULT_HOSTS = [
    "crsorgi.gov.in", "dc.crsorgi.gov.in", "edisha.gov.in", "online.ulbharyana.gov.in",
    "bnd.ndmc.gov.in", "mcdonline.nic.in", "pehchan.rajasthan.gov.in", "pehchan.raj.nic.in",
    "adjudication.igrmaharashtra.gov.in",
]


def _rules():
    f = Path(__file__).resolve().parent.parent / "rules.yaml"
    try:
        return yaml.safe_load(f.read_text())
    except Exception:
        return {}


def allowed_hosts():
    """Hosts the analyser opens (a verifier exists for them)."""
    return [h.lower() for h in _rules().get("allowed_hosts", DEFAULT_HOSTS)]


def _suffix_match(host, suffixes):
    host = (host or "").lower().rstrip(".")
    return any(host == h or host.endswith("." + h) for h in suffixes)


def host_allowed(host, hosts=None):
    return _suffix_match(host, hosts or allowed_hosts())


def is_government_host(host):
    return _suffix_match(host, _rules().get("government_suffixes", ["gov.in", "nic.in"]))


def render_pages(pdf_path, dpi):
    """Yield page images as BGR numpy arrays."""
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        for i in range(min(len(pdf), MAX_PAGES)):
            pil = pdf[i].render(scale=dpi / 72).to_pil().convert("RGB")
            yield cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    finally:
        pdf.close()


def _cv_decode(img):
    found = []
    detectors = [cv2.QRCodeDetector()]
    if hasattr(cv2, "QRCodeDetectorAruco"):
        detectors.append(cv2.QRCodeDetectorAruco())
    for det in detectors:
        try:
            ok, texts, _, _ = det.detectAndDecodeMulti(img)
            if ok:
                found += [t for t in texts if t]
            if not found:
                t, _, _ = det.detectAndDecode(img)
                if t:
                    found.append(t)
        except cv2.error:
            pass
        if found:
            break
    return found


def _zbar_decode(img):
    if not pyzbar:
        return []
    try:
        return [s.data.decode("utf-8", "replace") for s in pyzbar.decode(img, symbols=[ZBarSymbol.QRCODE])]
    except Exception:
        return []


def _variants(img):
    yield img
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    yield gray
    up = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    yield up
    yield cv2.threshold(up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    yield cv2.adaptiveThreshold(up, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 41, 10)


def decode_image(img):
    for v in _variants(img):
        for fn in (_cv_decode, _zbar_decode):
            found = fn(v)
            if found:
                return found
    return []


def embedded_images(pdf_path):
    """Yield embedded images at native resolution as BGR arrays (scanned or photographed uploads)."""
    try:
        reader = pypdf.PdfReader(str(pdf_path))
        for page in list(reader.pages)[:MAX_PAGES]:
            for im in page.images:
                try:
                    pil = Image.open(io.BytesIO(im.data)).convert("RGB")
                    yield cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
                except Exception:
                    continue
    except Exception:
        return


def _tiles(img, n=3, overlap=0.25):
    h, w = img.shape[:2]
    th, tw = int(h / n * (1 + overlap)), int(w / n * (1 + overlap))
    for i in range(n):
        for j in range(n):
            y, x = int(i * h / n), int(j * w / n)
            yield img[y:y + th, x:x + tw]


def decode_embedded(pdf_path):
    found = []
    for img in embedded_images(pdf_path):
        for t in decode_image(img):
            if t not in found:
                found.append(t)
        if found:
            break
        for tile in _tiles(img):
            for t in decode_image(tile):
                if t not in found:
                    found.append(t)
            if found:
                break
        if found:
            break
    return found


CACHE_VERSION = 2


def decode_pdf(pdf_path, use_cache=True):
    """Return unique QR payload strings found in the PDF (empty list = unreadable/none).

    Results are cached by file hash under store/cache/qr so re-runs are instant.
    """
    key = hashlib.sha256(Path(pdf_path).read_bytes()).hexdigest()
    cache_file = CACHE / f"{key}.json"
    if use_cache and cache_file.exists():
        data = json.loads(cache_file.read_text())
        if isinstance(data, dict) and data.get("v") == CACHE_VERSION:
            return data["payloads"]
        if isinstance(data, list) and data:  # old cache: a hit stays a hit, a miss is retried
            return data
    seen = []
    for dpi in DPIS:
        for page in render_pages(pdf_path, dpi):
            for text in decode_image(page):
                if text not in seen:
                    seen.append(text)
        if seen:
            break
    if not seen:
        seen = decode_embedded(pdf_path)
    CACHE.mkdir(parents=True, exist_ok=True)
    tmp = cache_file.with_suffix(f".{os.getpid()}.tmp")  # per process: parallel runs
    tmp.write_text(json.dumps({"v": CACHE_VERSION, "payloads": seen}))
    tmp.replace(cache_file)
    return seen


def diagnose(pdf_path):
    """Why was nothing decoded? 'located' = a QR shape was found but not readable."""
    pages = located = 0
    det = cv2.QRCodeDetector()
    for page in render_pages(pdf_path, 220):
        pages += 1
        gray = cv2.cvtColor(page, cv2.COLOR_BGR2GRAY)
        try:
            ok, _ = det.detectMulti(gray)
        except cv2.error:
            ok = False
        located += bool(ok)
    return "qr shape found but unreadable" if located else "no qr shape found"


def classify(text, hosts=None):
    """Classify one QR payload. Returns (kind, host).

    kind: official | mcd_text | fake_host | plain_text
      official / mcd_text  government host (gov.in / nic.in); genuine. MCD text carries 'Verified URL:'.
      fake_host            any other host, lookalikes included: REJECT
      court_case           eCourts case number (CNR) on a decree: no QR check, judge the decree text
      plain_text           no link in the QR: HOLD for DCRIM unless the rules know the format
    Use host_allowed(host) to know whether the analyser has a verifier and may open the link.
    """
    m = re.search(r"https?://[^\s|\"'<>]+", text)
    if not m:
        if re.fullmatch(r"[A-Za-z]{4}\d{12}", text.strip()):
            return "court_case", ""
        return "plain_text", ""
    host = urlparse(m.group(0)).hostname or ""
    if is_government_host(host):
        return ("mcd_text" if "Verified URL" in text else "official"), host
    return "fake_host", host


def best_link(payloads, hosts=None):
    """Pick the payload to act on: an official one first, else a fake_host, else None."""
    rank = {"official": 0, "mcd_text": 0, "fake_host": 1, "court_case": 2, "plain_text": 3}
    scored = sorted(((rank[classify(p, hosts)[0]], p) for p in payloads), key=lambda x: x[0])
    return scored[0][1] if scored else None


def shape(text):
    """Structure of a payload with content removed: letters -> a, digits -> 9."""
    t = re.sub(r"\d+", "9", re.sub(r"[^\W\d_]+", "a", text.strip()))
    return t[:40]


def report(modules):
    hosts = allowed_hosts()
    print("zbar fallback:", "available" if pyzbar else "not available (OpenCV only)")
    for module in modules:
        total = hit = 0
        kinds, host_count, errors, diag = Counter(), Counter(), Counter(), Counter()
        unread_by_type, plain_shapes = Counter(), Counter()
        listing, unread_ids = [], []
        for r, folder, err in load.load_module(module):
            if not r:
                continue
            total += 1
            if not r.pdf_path:
                errors["no pdf"] += 1
                continue
            try:
                payloads = decode_pdf(r.pdf_path)
            except Exception as e:
                errors[type(e).__name__] += 1
                continue
            if not payloads:
                kinds["unreadable/none"] += 1
                diag[diagnose(r.pdf_path)] += 1
                unread_by_type[r.request_type or "(blank)"] += 1
                unread_ids.append([r.id, r.request_type])
                continue
            hit += 1
            kind, host = classify(best_link(payloads, hosts), hosts)
            kinds[kind] += 1
            if kind == "plain_text":
                plain_shapes[shape(best_link(payloads, hosts))] += 1
                listing.append([r.id, shape(best_link(payloads, hosts))])
            if host:
                host_count[host] += 1
        print(f"\n== {load.MODULES[module]['title']} ==")
        print(f"requests: {total}   QR decoded: {hit} ({(100 * hit // total) if total else 0}%)")
        print("kinds:", dict(kinds))
        print("hosts:", dict(host_count))
        print("unreadable reasons:", dict(diag))
        print("unreadable by request type:", dict(unread_by_type))
        print("plain text shapes:", dict(plain_shapes))
        if listing:  # local file only: request ids per plain-text shape, to open by hand
            out = CACHE.parent.parent / f"qr_plain_text_{module}.csv"
            with open(out, "w", newline="") as fh:
                csv.writer(fh).writerows([["id", "shape"]] + sorted(listing, key=lambda x: x[1]))
            print("plain text ids written to", out)
        if unread_ids:
            out = CACHE.parent.parent / f"qr_unreadable_{module}.csv"
            with open(out, "w", newline="") as fh:
                csv.writer(fh).writerows([["id", "request_type"]] + unread_ids)
            print("unreadable ids written to", out)
        if errors:
            print("errors:", dict(errors))


if __name__ == "__main__":
    report(sys.argv[1:] or ["marital", "marriage"])
