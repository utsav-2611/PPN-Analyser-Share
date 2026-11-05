"""How do the weaker document types state the date of birth?  (DOB module; reads cached Vision text only.)

  python -m analyser.probe_dob_detail
Respects CRID_WORK_ROOT.  For each type: what kind of DOB statement each document carries (full date, year only, age as on
a date, nothing), the school state and register-copy signals of SLCs, and the most common masked line shapes near the
DOB, age and year words (a shape is printed only when at least MIN documents share it).  No names or numbers are printed.
Saves to store/probe_dob_detail.txt.
"""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from . import dobtext, load, match, vision_ocr
from .probe_dob_layout import mask
from .rules_dob import _school_state

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "store" / "probe_dob_detail.txt"
REF = ROOT / "reference" / "palwal_dob_recommendations.json"
GROUPS = ("Voter ID", "Electoral roll certificate", "School Leaving Certificate", "Middle School certificate",
          "Matriculation certificate", "Senior Secondary certificate")
NEAR = re.compile(r"birth|\bdob\b|d\.o\.b|\bage\b|year|dated|issued|date\b", re.I)
MIN = 3


def pages(path):
    try:
        import pypdf
        return len(pypdf.PdfReader(str(path)).pages)
    except Exception:
        return 0


def main():
    lines = ["probe_dob_detail v1 (counts and masked shapes only)", f"work root: {load.WORK_ROOT}"]
    reqs = {r.request_id: r for r, _, _ in load.load_module("dob") if r}
    items = {str(it["requestId"]): it for it in json.loads(REF.read_text(encoding="utf-8"))["items"]}
    for group in GROUPS:
        kinds, shapes, extra = Counter(), Counter(), Counter()
        n = 0
        for rid, r in sorted(reqs.items()):
            if items.get(rid, {}).get("docType") != group or not r.pdf_path:
                continue
            text = vision_ocr.cached_text(r.pdf_path)
            if text is None:
                extra["no vision text"] += 1
                continue
            n += 1
            new = match.parse_date(r.user_info.get("Requested DOB"))
            found = dobtext.find_dob(text, new)
            dates, years = dobtext.dob_context(text, same_line=group in ("Voter ID", "Electoral roll certificate"))
            ages = dobtext.ages_as_on(text)
            kind = ("age as on" if ages else "age without date" if dobtext.plain_ages(text) else "full date on DOB line" if dates else "year only on DOB line" if years else
                    "date elsewhere only" if dobtext.dates_in(text) else "nothing")
            kinds[f"{kind}; requested {'exact' if found == 'exact' else 'one digit off' if found else 'not found'}"] += 1
            if group == "School Leaving Certificate":
                extra["pages>=2"] += pages(r.pdf_path) >= 2
                extra["word 'register' in text"] += bool(re.search("register", text, re.I))
                extra["state " + _school_state(text)] += 1
                extra["label mentions school record copy"] += "copy of school record" in str(r.user_info.get("Uploaded Document", "")).lower()
            if found != "exact":
                seen = {mask(l) for l in text.splitlines() if NEAR.search(l)}
                for sh in seen:
                    if sh and len(sh) > 3:
                        shapes[sh] += 1
        lines.append(f"\\n=== {group}: {n} documents with Vision text ===")
        lines.append("   " + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items(), key=lambda kv: -kv[1])))
        if extra:
            lines.append("   " + ", ".join(f"{k} {v}" for k, v in sorted(extra.items())))
        lines.append(f"   common line shapes near birth / age / year words in documents where the requested DOB was NOT found (>= {MIN}):")
        for sh, c in shapes.most_common(18):
            if c >= MIN:
                lines.append(f"      x{c}  {sh[:110]}")
    text = "\n".join(lines).replace("\\n", "\n")
    OUT.write_text(text)
    print(text)
    print("\nsaved to", OUT)


if __name__ == "__main__":
    main()
