"""Which OCR finds the requested date of birth most often?  (DOB module, ~80 sampled documents.)

  python -m analyser.probe_ocr_compare
Respects CRID_WORK_ROOT.  Local only: tesseract and Apple Vision, no internet.
Engines: tess_now (the cached 200 dpi eng+hin text from the other probes), tess_300 (300 dpi, contrast clean-up,
eng+hin, psm 6) and vision (Apple Vision, English).  Prints counts and seconds only, never any text.
Results are cached in store/cache/ocr_compare/, so a second run is quick.  Saves to store/probe_ocr_compare.txt.
"""
import hashlib
import io
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from . import dobtext, electors, load, match, ocr

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "store" / "probe_ocr_compare.txt"
REF = ROOT / "reference" / "palwal_dob_recommendations.json"
CACHE = ROOT / "store" / "cache" / "ocr_compare"
VERSION = 1
PAGES, DPI = 3, 300
WANT = {"Matriculation certificate": 30, "School Leaving Certificate": 25, "Voter ID": 25}
ENGINES = ("tess_now", "tess_300", "vision")


def render(pdf_path):
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        return [pdf[i].render(scale=DPI / 72).to_pil().convert("RGB") for i in range(min(len(pdf), PAGES))]
    finally:
        pdf.close()


def tess_300(images):
    import cv2
    import numpy as np
    import pytesseract
    parts = []
    for im in images:
        gray = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2GRAY)
        gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
        parts.append(pytesseract.image_to_string(gray, lang="eng+hin", config="--psm 6"))
    return "\n".join(parts)


def vision(images):
    import Foundation
    import objc
    import Vision
    parts = []
    for im in images:
        with objc.autorelease_pool():
            buf = io.BytesIO()
            im.save(buf, "PNG")
            data = Foundation.NSData.dataWithBytes_length_(buf.getvalue(), len(buf.getvalue()))
            req = Vision.VNRecognizeTextRequest.alloc().init()
            req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
            req.setRecognitionLanguages_(["en-US"])
            handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(data, None)
            handler.performRequests_error_([req], None)
            lines = [o.topCandidates_(1)[0].string() for o in (req.results() or []) if o.topCandidates_(1)]
            parts.append("\n".join(lines))
    return "\n".join(parts)


RUN = {"tess_300": tess_300, "vision": vision}


def text_for(engine, pdf_path, key, images_box):
    """(text, seconds) or (None, 0) when the engine cannot run."""
    if engine == "tess_now":
        got = ocr.cached_text(pdf_path)
        return (got[0], 0.0) if got else (None, 0.0)
    f = CACHE / f"{key}.{engine}.v{VERSION}.json"
    if f.exists():
        d = json.loads(f.read_text(encoding="utf-8"))
        return d["text"], d["seconds"]
    try:
        if images_box[0] is None:
            images_box[0] = render(pdf_path)
        t0 = time.time()
        text = RUN[engine](images_box[0])
        secs = time.time() - t0
    except Exception as e:  # engine missing or failed: report once, keep going
        print(f"   {engine} failed: {type(e).__name__}", file=sys.stderr)
        return None, 0.0
    f.write_text(json.dumps({"text": text, "seconds": secs}, ensure_ascii=False), encoding="utf-8")
    f.chmod(0o600)
    return text, secs


def sample(reqs, items):
    by = defaultdict(list)
    for rid, r in sorted(reqs.items()):
        t = items.get(rid, {}).get("docType")
        if t in WANT and r.pdf_path:
            by[t].append(r)
    out = {}
    for t, n in WANT.items():
        rs = by[t]
        step = max(len(rs) / n, 1)
        out[t] = [rs[int(i * step)] for i in range(min(n, len(rs)))]
    return out


def main():
    lines = ["probe_ocr_compare v1 (counts and seconds only)", f"work root: {load.WORK_ROOT}"]
    CACHE.mkdir(parents=True, exist_ok=True)
    CACHE.chmod(0o700)
    reqs = {r.request_id: r for r, _, _ in load.load_module("dob") if r}
    items = {str(it["requestId"]): it for it in json.loads(REF.read_text(encoding="utf-8"))["items"]}
    chosen = sample(reqs, items)
    total, done = sum(len(v) for v in chosen.values()), 0
    for group, rs in chosen.items():
        stats = {e: Counter() for e in ENGINES}
        union = Counter()
        for r in rs:
            done += 1
            print(f"   {done}/{total}", file=sys.stderr)
            key = hashlib.sha256(r.pdf_path.read_bytes()).hexdigest()[:32]
            box = [None]
            req = match.parse_date(r.user_info.get("Requested DOB"))
            ppp = match.parse_date(r.user_info.get("DOB In PPP"))
            docvars = electors.variants(r.user_info.get("Document Number", "")) if group == "Voter ID" else []
            hit = {}
            for e in ENGINES:
                text, secs = text_for(e, r.pdf_path, key, box)
                s = stats[e]
                if text is None:
                    s["not available"] += 1
                    continue
                s["docs"] += 1
                s["seconds"] += secs
                s["words<30"] += len(re.findall(r"\w+", text)) < 30
                s["any date"] += bool(dobtext.dates_in(text))
                found = dobtext.find_dob(text, req)
                s["requested exact"] += found == "exact"
                s["requested one digit off"] += found == "one digit off"
                s["PPP exact (old date shown)"] += dobtext.find_dob(text, ppp) == "exact" and ppp != req
                s["age-as-on line"] += bool(dobtext.ages_as_on(text))
                if docvars:
                    flat = re.sub(r"[^A-Z0-9]", "", text.upper())
                    s["EPIC in text"] += any(v in flat for v in docvars)
                hit[e] = found
            for e, f in hit.items():
                others = [hit[o] for o in hit if o != e]
                if f == "exact" and "exact" not in others:
                    union[f"exact only by {e}"] += 1
            union["exact by any engine"] += "exact" in hit.values()
            union["exact or one digit off by any engine"] += any(hit.values())
            union["documents"] += 1
        lines.append(f"\n=== {group}: {len(rs)} sampled ===")
        for e in ENGINES:
            s = stats[e]
            n = s["docs"]
            avg = f"{s['seconds'] / n:.1f}s/doc" if n and e != "tess_now" else "-"
            lines.append(f"   {e}: " + ", ".join(f"{k} {v}" for k, v in s.items() if k not in ("seconds", "docs")) +
                         f"   (docs {n}, {avg})")
        lines.append("   " + ", ".join(f"{k} {v}" for k, v in union.items()))
    text = "\n".join(lines)
    OUT.write_text(text)
    print(text)
    print("\nsaved to", OUT)


if __name__ == "__main__":
    main()
