"""Structure of the collected DOB requests with every value masked (letters a, digits 9).

  python -m analyser.probe_dob
Respects CRID_WORK_ROOT (and ELECTORS_DB for the electoral roll).  Prints and saves to store/probe_dob.txt.
Prints labels, counts and masked shapes only: no names, numbers or addresses.
"""
import os
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from . import load, qr

OUT = Path(__file__).resolve().parent.parent / "store" / "probe_dob.txt"
KEYWORDS = {
    "voter/epic": r"election commission|elector|epic|voter|मतदाता|निर्वाचन",
    "matric/board": r"matriculation|secondary education|board of school|माध्यमिक|बोर्ड",
    "school leaving": r"school leaving|transfer certificate|admission|withdrawal|विद्यालय छोड़ने|प्रवेश",
    "passport": r"passport|republic of india",
    "birth certificate": r"birth|जन्म",
    "electoral roll": r"electoral roll|part no|मतदाता सूची|diary",
    "aadhaar": r"aadhaar|आधार|unique identification",
    "driving/pan/id": r"driving|permanent account|identity card|पहचान पत्र",
}


def top(counter, n=6):
    return ", ".join(f"{k!r} x{v}" for k, v in counter.most_common(n))


def electors_report(lines):
    path = Path(os.environ.get("ELECTORS_DB") or load.WORK_ROOT / "Electors" / "electors.db")
    lines.append(f"\n--- electoral roll database: {'found' if path.exists() else 'NOT FOUND'} ---")
    if not path.exists():
        return
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        for (name, sql) in con.execute("select name, sql from sqlite_master where type in ('table','index') and sql is not null"):
            lines.append(f"   {sql}")
            if sql.startswith("CREATE TABLE"):
                lines.append(f"   rows in {name}: {con.execute(f'select count(*) from [{name}]').fetchone()[0]}")
        cols = [r[1] for r in con.execute("pragma table_info(electors)")]
        if "epic" in cols:
            shapes = Counter(qr.shape(str(e or "")) for (e,) in con.execute("select epic from electors"))
            lines.append(f"   epic shapes: {top(shapes)}")
        if "age_as_on" in cols:
            lines.append(f"   age_as_on shapes: {top(Counter(qr.shape(str(e or '')) for (e,) in con.execute('select distinct age_as_on from electors')))}")
        if "name" in cols:
            dev = sum(1 for (n,) in con.execute("select name from electors limit 5000") if re.search(r"[ऀ-ॿ]", n or ""))
            lines.append(f"   names with Devanagari in first 5000 rows: {dev}")
    finally:
        con.close()


def main(documents=True, out=OUT):
    lines = ["probe_dob v1" + ("" if documents else " quick, no documents") + " (masked output only)", f"work root: {load.WORK_ROOT}"]
    reqs, errors = [], Counter()
    for r, folder, err in load.load_module("dob"):
        if r:
            reqs.append(r)
        else:
            errors[err] += 1
    lines.append(f"requests loaded: {len(reqs)}   unreadable case.json: {sum(errors.values())} {dict(errors) or ''}")
    if not reqs:
        electors_report(lines)
        print("\n".join(lines))
        return

    lines.append(f"tabs: {dict(Counter(r.tab for r in reqs))}")
    lines.append(f"module title: {top(Counter(str(r.raw.get('module')) for r in reqs))}")
    lines.append(f"top-level keys: {top(Counter(k for r in reqs for k in r.raw), 40)}")
    lines.append(f"fieldsets (case keys): {top(Counter(k for r in reqs for k in r.case), 40)}")
    lines.append(f"list_row keys: {top(Counter(k for r in reqs for k in r.list_row), 40)}")
    lines.append(f"files: pdf {sum(1 for r in reqs if r.pdf_path)}  png {sum(1 for r in reqs if r.window_png)}  "
                 f"document_files lengths {top(Counter(len(r.raw.get('document_files') or []) for r in reqs))}")
    lines.append(f"family table: {top(Counter('none' if r.family() is None else 'rows=%d' % len(r.family()) for r in reqs), 12)}")
    lines.append(f"family columns: {top(Counter(k for r in reqs for row in (r.family() or []) for k in row), 20)}")
    lines.append(f"other row-list keys: {top(Counter(k for r in reqs for k, v in r.raw.items() if isinstance(v, list) and k != 'family'))}")
    lines.append(f"subordinate remark blocks: {top(Counter(role for r in reqs for role, _, _ in r.subordinate_remarks()))}")
    lines.append(f"remark block fields: {top(Counter(k for r in reqs for _, _, b in r.subordinate_remarks() for k in b), 10)}")
    lines.append(f"Flag values: {top(Counter(load.get(r.list_row, 'Flag') or '-' for r in reqs))}")
    for key in ("Request Type", "Current Status", "Status"):
        c = Counter(load.get(r.list_row, key) or "-" for r in reqs)
        if len(c) > 1 or "-" not in c:
            lines.append(f"list_row {key}: {top(c)}")

    # every fieldset: label -> filled count and the most common masked value shapes
    lines.append("\n--- fieldset labels (filled/total) and masked value shapes ---")
    for legend in sorted({k for r in reqs for k in r.case}):
        labels = defaultdict(Counter)
        for r in reqs:
            sec = r.case.get(legend)
            if isinstance(sec, dict):
                for k, v in sec.items():
                    if isinstance(v, (dict, list)):
                        labels[k]["<%s>" % type(v).__name__] += 1
                    else:
                        labels[k][qr.shape(str(v)) if str(v).strip() else "<empty>"] += 1
        lines.append(f"[{legend}]")
        for k, c in sorted(labels.items(), key=lambda kv: -sum(kv[1].values())):
            filled = sum(n for s, n in c.items() if s != "<empty>")
            lines.append(f"   {k}: {filled}/{len(reqs)}   {top(c, 5)}")

    if not documents:
        electors_report(lines)
        text = "\n".join(lines)
        out.write_text(text)
        print(text)
        print("\nsaved to", out)
        return

    # document and QR
    lines.append("\n--- documents ---")
    methods, pages, qr_kinds, hosts, kw = Counter(), Counter(), Counter(), Counter(), Counter()
    words = Counter()
    kw_by_label = defaultdict(Counter)
    doc_label_key = None
    for r in reqs:
        for k in r.user_info:
            if re.search(r"document|proof", load.norm(k)):
                doc_label_key = doc_label_key or k
    for r in reqs:
        if not r.pdf_path:
            continue
        payloads = qr.decode_pdf(r.pdf_path)
        qr_kinds[qr.classify(qr.best_link(payloads) or "")[0] if payloads else "no_qr"] += 1
        for p in payloads:
            kind, host = qr.classify(p)
            hosts[f"{kind}:{host}"] += 1
        try:
            from . import ocr
            text, info = ocr.text_of(r.pdf_path)
        except Exception as e:
            methods["error:" + type(e).__name__] += 1
            continue
        methods[info["method"]] += 1
        pages[info["pages"]] += 1
        words[min(len(re.findall(r"\w+", text)) // 100 * 100, 1000)] += 1
        found = [name for name, pat in KEYWORDS.items() if re.search(pat, text, re.I)]
        for name in found:
            kw[name] += 1
        label = r.user_info.get(doc_label_key, "-") if doc_label_key else "-"
        for name in found:
            kw_by_label[str(label)[:40]][name] += 1
    lines.append(f"QR best kind: {top(qr_kinds)}")
    lines.append(f"QR hosts: {top(hosts, 15)}")
    lines.append(f"text method: {top(methods)}   pages: {top(pages)}   words bucket(100s): {top(words, 12)}")
    lines.append(f"keyword hits (documents containing): {top(kw, 12)}")
    if doc_label_key:
        lines.append(f"request document label '{doc_label_key}' vs keywords found:")
        for label, c in kw_by_label.items():
            lines.append(f"   {label!r}: {top(c, 8)}")
    electors_report(lines)
    text = "\n".join(lines)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(text)
    print(text)
    print("\nsaved to", OUT)


if __name__ == "__main__":
    main()
