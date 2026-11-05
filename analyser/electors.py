"""Read-only lookup in the electoral roll database (load.ELECTORS_DB) for the DOB voter-card check.

Table `electors`: ac_no, ac_name, part_no, serial_no, epic, name, relation_type, relation_name, house_no, age,
gender, age_as_on, section, deleted, ... Names are in Hindi. EPICs are mostly `ABC1234567`; about a fifth are old
style `HR/12/123/456789`, so both sides are compared with spaces and slashes removed.
"""
import re
import sqlite3

from . import load

COLUMNS = ("ac_no", "ac_name", "part_no", "serial_no", "epic", "name", "relation_type", "relation_name",
           "house_no", "age", "gender", "age_as_on", "deleted")


def normalize_epic(epic):
    """Upper case, only letters and digits: 'hr/12/123/456789' -> 'HR12123456789'."""
    return re.sub(r"[^A-Z0-9]", "", str(epic or "").upper())


def variants(epic):
    """The two EPIC spellings to try, normalised: the last number as given, and with its leading 0 flipped (a 0
    added in front, or the leading 0 removed when there is one). The last number is the part after the last slash,
    or the trailing digits when there is no slash."""
    text = re.sub(r"\s+", "", str(epic or "").upper())
    if "/" in text:
        head, _, last = text.rpartition("/")
        head += "/"
    else:
        m = re.fullmatch(r"(.*?)(\d+)", text)
        head, last = (m.group(1), m.group(2)) if m else (text, "")
    if not last:
        return [normalize_epic(text)] if text else []
    flipped = last[1:] if last.startswith("0") else "0" + last
    return [normalize_epic(head + last), normalize_epic(head + flipped)]


def lookup(epic, db_path=None):
    """Rows (dicts) whose EPIC equals `epic` or one of its zero variants; each row has `matched_epic`.
    [] when not found or the database is missing."""
    want = variants(epic)
    path = db_path or load.ELECTORS_DB
    if not want or len(want[0]) < 6 or not path or not path.exists():
        return []
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        cols = ", ".join(COLUMNS)
        marks = ",".join("?" * len(want))
        # indexed exact match first, then the slower comparison that ignores slashes and spaces
        rows = con.execute(f"select {cols} from electors where epic in ({marks})", want).fetchall()
        if not rows:
            rows = con.execute(
                f"select {cols} from electors where upper(replace(replace(epic, '/', ''), ' ', '')) in ({marks})", want
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["matched_epic"] = normalize_epic(d["epic"])
            out.append(d)
        return out
    finally:
        con.close()
