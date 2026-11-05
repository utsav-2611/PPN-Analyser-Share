"""Find the issuing state of certificates that have no readable QR.

  python -m analyser.issuer
Prints counts only; request ids per result go to store/issuer_noqr.csv (local file).
"""
import csv
import re
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import pypdf
import pypdfium2 as pdfium
import pytesseract
from PIL import Image

from . import load, qr

HEADER_FRACTION = 0.35   # top part of page 1 holds the issuing authority
OUT = Path(__file__).resolve().parent.parent / "store" / "issuer_noqr.csv"
STATES = {
    "haryana": r"haryana|हरियाणा|हरयाणा",
    "delhi": r"delhi|दिल्ली|ndmc|mcd\b",
    "punjab": r"punjab|पंजाब",
    "uttar pradesh": r"uttar\s*pradesh|उत्तर\s*प्रदेश",
    "rajasthan": r"rajasthan|राजस्थान",
    "himachal": r"himachal|हिमाचल",
    "uttarakhand": r"uttarakhand|उत्तराखंड|उत्तराखण्ड",
    "madhya pradesh": r"madhya\s*pradesh|मध्य\s*प्रदेश",
    "bihar": r"bihar|बिहार",
    "maharashtra": r"maharashtra|महाराष्ट्र",
    "gujarat": r"gujarat|गुजरात",
    "chandigarh": r"chandigarh|चंडीगढ़|चण्डीगढ़",
    "jammu kashmir": r"jammu|kashmir|जम्मू",
}
NON_GOVT = r"society|samaj|sabha|mandir|temple|trust|ashram|agreement|affidavit|notary|समाज|मंदिर|ट्रस्ट|शपथ|एफिडेविट"


def header_text(pdf_path):
    """Text of the top part of page 1: text layer if present, else OCR (eng+hin)."""
    try:
        layer = (pypdf.PdfReader(str(pdf_path)).pages[0].extract_text() or "")[:700]
    except Exception:
        layer = ""
    if len(re.sub(r"\W", "", layer)) > 80:
        return layer, "text layer"
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        pil = pdf[0].render(scale=200 / 72).to_pil().convert("L")
    finally:
        pdf.close()
    w, h = pil.size
    top = pil.crop((0, 0, w, int(h * HEADER_FRACTION)))
    return pytesseract.image_to_string(top, lang="eng+hin"), "ocr"


MAX_PAGES = 6
ISSUER_PHRASE = (r"(?:government|govt\.?|state)\s+of\s+(?:nct\s+of\s+)?(?:{s})"
                 r"|(?:{s})\s+(?:government|govt\.?|state|sarkar|सरकार)|सरकार\s+(?:{s})")


def ocr_page(pil):
    """OCR one page; fix sideways or upside-down scans using tesseract's orientation detection."""
    try:
        osd = pytesseract.image_to_osd(pil)
        angle = int(re.search(r"Rotate: (\d+)", osd).group(1))
        if angle:
            pil = pil.rotate(-angle, expand=True)
    except Exception:
        pass
    return pytesseract.image_to_string(pil, lang="eng+hin")


def full_text(pdf_path):
    """All pages (text layer plus OCR). Slower: used only for headings that could not be read."""
    parts = []
    try:
        parts += [(pg.extract_text() or "") for pg in list(pypdf.PdfReader(str(pdf_path)).pages)[:MAX_PAGES]]
    except Exception:
        pass
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        for i in range(min(len(pdf), MAX_PAGES)):
            parts.append(ocr_page(pdf[i].render(scale=200 / 72).to_pil().convert("L")))
    finally:
        pdf.close()
    return "\n".join(parts)


def classify_issuer_phrase(text):
    """Stricter than classify(): only 'Government of <state>' style phrases count, because an
    address elsewhere on the page can name Haryana for a certificate issued by another state."""
    t = text.lower()
    if re.search(NON_GOVT, t):
        return "non government", ""
    hits = [s for s, pat in STATES.items() if re.search(ISSUER_PHRASE.format(s=pat), t)]
    if len(hits) == 1:
        return hits[0], ""
    if len(hits) > 1:
        return "mixed", "/".join(hits)
    return "unknown", ""


def classify(text):
    """('haryana'|'<other state>'|'non government'|'unknown', note)"""
    t = text.lower()
    if re.search(NON_GOVT, t):
        return "non government", ""
    hits = [s for s, pat in STATES.items() if re.search(pat, t)]
    if "haryana" in hits and len(hits) == 1:
        return "haryana", ""
    if len(hits) == 1:
        return hits[0], ""
    if len(hits) > 1:
        return "mixed", "/".join(hits)
    return "unknown", ""


def issuer_of(pdf_path):
    """(state, read_by, note) for one certificate: heading first, then the full-page pass.

    state is 'haryana', another state name, 'non government', 'mixed' or 'unknown'.
    """
    text, how = header_text(pdf_path)
    state, note = classify(text)
    if state in ("unknown", "mixed"):
        state2, note2 = classify_issuer_phrase(full_text(pdf_path))
        if state2 not in ("unknown", "mixed"):
            return state2, "full page", note2
    return state, how, note


def main():
    print("issuer v2 (counts only)")
    rows, summary, by_type = [], Counter(), Counter()
    for module in ("marital", "marriage"):
        for r, _, _ in load.load_module(module):
            if not r or not r.pdf_path or r.request_type == "Divorced":
                continue
            if qr.decode_pdf(r.pdf_path):
                continue
            try:
                text, how = header_text(r.pdf_path)
                state, note = classify(text)
            except Exception as e:
                state, how, note = "error " + type(e).__name__, "-", ""
            if state in ("unknown", "mixed"):  # second pass: every page, rotated if needed
                try:
                    state2, note2 = classify_issuer_phrase(full_text(r.pdf_path))
                except Exception as e:
                    state2, note2 = "error " + type(e).__name__, ""
                if state2 not in ("unknown", "mixed") and not state2.startswith("error"):
                    state, how, note = state2, "full page", note2
                elif state2 == "mixed":
                    note = note2
            summary[state] += 1
            by_type[(r.request_type or "(blank)", "haryana" if state == "haryana" else "other/unknown")] += 1
            rows.append([r.id, r.request_type, state, how, note])
    print("no QR / unreadable (excluding Divorced):", len(rows))
    for state, n in summary.most_common():
        print(f"  {state}: {n}")
    print("by request type (Haryana vs other/unknown):")
    for (t, k), n in sorted(by_type.items()):
        print(f"  {t} / {k}: {n}")
    print("read by:", dict(Counter(r[3] for r in rows)))
    OUT.parent.mkdir(exist_ok=True)
    with open(OUT, "w", newline="") as fh:
        csv.writer(fh).writerows([["id", "request_type", "issuer", "read_by", "note"]] + rows)
    print("details saved to", OUT)


if __name__ == "__main__":
    main()
