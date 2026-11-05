"""Where and how the DOB appears in the OCR text of each document type (DOB module), values masked.

  python -m analyser.probe_dob_layout
Respects CRID_WORK_ROOT.  Reads only OCR text that is already cached (never runs OCR, never opens the internet).
Prints counts and masked sample lines: a word is kept only if it is in the label vocabulary below, every other word
becomes a, every digit 9.  Groups use the document type in the reference file.  Saves to store/probe_dob_layout.txt.
"""
import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from . import load, match, ocr

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "store" / "probe_dob_layout.txt"
REF = ROOT / "reference" / "palwal_dob_recommendations.json"
SAMPLES, LINES = 3, 14

MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]
VOCAB = set(MONTHS) | {m[:3] for m in MONTHS} | set("""
date of birth dob d o b age years year months month days day on as issued issue dated place sex gender male female
name father mother husband wife guardian son daughter spouse relation elector electors epic no number part serial
roll assembly constituency election commission india identity card photo identity school class admission register
withdrawal leaving certificate transfer board secondary education senior middle matriculation examination roll
candidate certified that born in figures words passport republic nationality surname given birth place issue expiry
government of haryana signature principal seal village district tehsil state sr resident address
जन्म तिथि दिनांक आयु वर्ष माह पिता माता पति पत्नी नाम लिंग पुरुष महिला निर्गत मतदाता पहचान पत्र क्रमांक भाग
विद्यालय विद्यालय प्रवेश कक्षा प्रमाण प्रमाणपत्र बोर्ड हरियाणा सरकार
""".split())
KEYWORD = re.compile(r"birth|dob|d\.o\.b|age\b|years|dated|issued|epic|elector|नाम|जन्म|आयु|दिनांक|वर्ष|निर्गत|तिथि", re.I)
DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
NUM_DATE = re.compile(r"(?<!\d)(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{4})(?!\d)")
NAME_DATE = re.compile(r"(?<!\d)(\d{1,2})\s*(?:st|nd|rd|th)?[\s,\-]*(" + "|".join(m[:3] for m in MONTHS) +
                       r")[a-z]*[\s,\-]*(\d{4})(?!\d)", re.I)
NAME_DATE_US = re.compile(r"(" + "|".join(m[:3] for m in MONTHS) + r")[a-z]*\s+(\d{1,2})\s*(?:st|nd|rd|th)?,?\s+(\d{4})(?!\d)", re.I)
WORDS_DATE = re.compile(r"(nineteen|two thousand|one thousand nine hundred)", re.I)


def mask(line):
    out = []
    for tok in re.findall(r"(?:[^\W\d_]|[\u0900-\u097F])+|\d+|[^\w\s]|\s+", line.translate(DEV_DIGITS)):
        if tok.isspace():
            out.append(" ")
        elif tok.isdigit():
            out.append("9")
        elif tok[0].isalpha() or "\u0900" <= tok[0] <= "\u097F":
            out.append(tok if tok.lower() in VOCAB else "a")
        else:
            out.append(tok)
    return re.sub(r" +", " ", "".join(out)).strip()


def dates_in(text):
    text = text.translate(DEV_DIGITS)
    found = set()
    for d, m, y in NUM_DATE.findall(text):
        try:
            found.add(date(int(y), int(m), int(d)))
        except ValueError:
            pass
    for d, mon, y in NAME_DATE.findall(text):
        try:
            found.add(date(int(y), [m[:3] for m in MONTHS].index(mon.lower()[:3]) + 1, int(d)))
        except ValueError:
            pass
    for mon, d, y in NAME_DATE_US.findall(text):
        try:
            found.add(date(int(y), [m[:3] for m in MONTHS].index(mon.lower()[:3]) + 1, int(d)))
        except ValueError:
            pass
    return found


def pct(n, total):
    return f"{n}/{total}"


def main():
    lines = ["probe_dob_layout v1 (masked output only; cached OCR text only)", f"work root: {load.WORK_ROOT}"]
    reqs = {r.request_id: r for r, _, _ in load.load_module("dob") if r}
    items = {str(it["requestId"]): it for it in json.loads(REF.read_text(encoding="utf-8"))["items"]}
    groups = defaultdict(list)
    for rid, r in sorted(reqs.items()):
        if r.pdf_path:
            groups[items.get(rid, {}).get("docType", "(not in reference)")].append(r)
    for gname, rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        stats = Counter()
        shapes = Counter()
        samples = []
        for r in rs:
            got = ocr.cached_text(r.pdf_path)
            if got is None:
                stats["not cached yet"] += 1
                continue
            text, info = got
            stats["cached"] += 1
            stats["method " + info["method"]] += 1
            stats["pages " + str(min(info["pages"], 5))] += 1
            ds = dates_in(text)
            stats["has any date"] += bool(ds)
            req = match.parse_date(r.user_info.get("Requested DOB"))
            ppp = match.parse_date(r.user_info.get("DOB In PPP"))
            stats["requested DOB found in text"] += bool(req and req in ds)
            stats["PPP DOB found in text"] += bool(ppp and ppp in ds)
            stats["either found"] += bool((req and req in ds) or (ppp and ppp in ds))
            if req and ppp and req != ppp:
                stats["DOB changed"] += 1
                stats["changed: requested found"] += bool(req in ds)
                stats["changed: PPP found"] += bool(ppp in ds)
            stats["numeric dd/mm/yyyy"] += bool(NUM_DATE.search(text.translate(DEV_DIGITS)))
            stats["day month-name year"] += bool(NAME_DATE.search(text) or NAME_DATE_US.search(text))
            stats["date in words"] += bool(WORDS_DATE.search(text))
            stats["Devanagari text"] += bool(re.search(r"[ऀ-ॿ]{3}", text))
            stats["English 'date of birth'"] += bool(re.search(r"date\s+of\s+birth|d\.?o\.?b", text, re.I))
            stats["Hindi जन्म"] += "जन्म" in text
            docno = re.sub(r"[^A-Z0-9]", "", str(r.user_info.get("Document Number", "")).upper())
            if len(docno) >= 6:
                stats["with usable doc number"] += 1
                stats["doc number found in text"] += docno in re.sub(r"[^A-Z0-9]", "", text.translate(DEV_DIGITS).upper())
            stats["words<100"] += len(re.findall(r"\w+", text)) < 100
            if len(samples) < SAMPLES and len(re.findall(r"\w+", text)) >= 30:
                kept = [mask(l) for l in text.splitlines() if l.strip() and KEYWORD.search(l)]
                samples.append([k for k in kept if k][:LINES])
        lines.append(f"\n=== {gname}: {len(rs)} requests with a PDF ===")
        lines.append("   " + ", ".join(f"{k} {v}" for k, v in sorted(stats.items())))
        for i, smp in enumerate(samples, 1):
            lines.append(f"   sample {i}:")
            lines.extend("      " + s for s in smp)
    text = "\n".join(lines)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(text)
    print(text)
    print("\nsaved to", OUT)


if __name__ == "__main__":
    main()
