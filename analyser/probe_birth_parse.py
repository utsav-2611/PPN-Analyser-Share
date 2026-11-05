"""Why do some cached CRS birth pages not parse?  Cache only, no network.

  python -m analyser.probe_birth_parse
Parses every cached CRS birth page with crs_birth.parse.  For pages where it fails (no DOB or registration number) it prints
the lines that recur across at least 3 failing pages (fixed page labels), raw, with the number of cells and how many pages have
them; everything else is counted, never printed.  Saves to store/probe_birth_parse.txt.
"""
import json
import re
from collections import Counter
from pathlib import Path

from . import qr
from .verify import crs_birth
from .verify.base import CACHE

OUT = Path(__file__).resolve().parent.parent / "store" / "probe_birth_parse.txt"
MIN = 3


def main():
    lines = ["probe_birth_parse v1 (fixed labels only; counts)"]
    ok = fail = 0
    cells = Counter()
    values = Counter()
    for f in sorted(CACHE.glob("*.crsbirth.json")):
        text = json.loads(f.read_text(encoding="utf-8"))["text"]
        fields = crs_birth.parse(text)
        if "dob" in fields and "reg_no" in fields:
            ok += 1
            continue
        fail += 1
        seen = set()
        for line in text.splitlines():
            parts = [p.strip() for p in re.split(r"\t|\s{3,}", line.strip()) if p.strip()]
            if len(parts) == 2 and parts[0] in ("DOB", "Registration Number", "Registration Date"):
                values[f"{parts[0]}: {qr.shape(parts[1])}"] += 1
            if parts:
                seen.add((len(parts), parts[0][:60]))
        cells.update(seen)
    lines.append(f"cached pages: parsed ok {ok}, failed {fail}")
    lines.append(f"lines found on at least {MIN} failing pages (cells, first cell, pages):")
    for (n, first), c in sorted(cells.items(), key=lambda kv: -kv[1]):
        if c >= MIN:
            lines.append(f"   {n} cell(s)  {first!r}  x{c}")
    lines.append("masked shapes of the date and number cells on the failing pages:")
    lines.extend(f"   {k}  x{v}" for k, v in sorted(values.items()))
    text = "\n".join(lines)
    OUT.write_text(text)
    print(text)
    print("\nsaved to", OUT)


if __name__ == "__main__":
    main()
