"""Print or export the analysed requests.

  python -m analyser.report                 counts by module and recommendation
  python -m analyser.report --csv out.csv   one row per request: recommendation, remark, reject reason, flags, analysis
"""
import argparse
import csv
from collections import Counter

from . import store

COLUMNS = ("module", "requestId", "recommendation", "proposedRemark", "rejectReason", "notes", "analysis")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="write one row per request to this file")
    args = ap.parse_args(argv)
    requests = store.read()["requests"].values()
    for module in sorted({r["module"] for r in requests}):
        print(module, dict(Counter(r["recommendation"] for r in requests if r["module"] == module)))
    print("total", len(requests))
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(COLUMNS)
            w.writerows([r.get(c, "") for c in COLUMNS] for r in requests)
        print("written:", args.csv)


if __name__ == "__main__":
    main()
