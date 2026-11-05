"""Shared parsing of death-certificate records from CRS, NDMC and MCD pages.

parse(text) -> dict with keys among: name, gender, dod, place, father, mother, spouse, reg_no, reg_date, unit
(dates as ISO yyyy-mm-dd).  The sites lay a record out differently, so labelled values are accepted as

  A  'Label : value'           on one line
  B  'Label<TAB>value'         table row
  C  'Label' newline 'value'   value on the following line
  D  a block of labels followed by a block of values in the same order
"""
import re
from html.parser import HTMLParser

from .. import decree, match
from ..load import norm

SYNONYMS = {
    "name": ["name", "name of deceased", "name of the deceased", "deceased name", "name of deceased person", "name of the deceased person"],
    "gender": ["gender", "sex"],
    "dod": ["date of death", "dod", "death date", "date of death dd mm yyyy", "date of event"],
    "place": ["place of death", "death place", "place of event"],
    "activity": ["activity type", "event", "event type"],
    "father": ["name of father", "father name", "father s name", "fathers name", "name of the father", "father"],
    "mother": ["name of mother", "mother name", "mother s name", "mothers name", "name of the mother", "mother"],
    "spouse": ["name of husband", "husband name", "husband s name", "name of spouse", "spouse name", "name of husband wife",
               "husband wife name", "name of the husband", "husband", "spouse", "name of wife", "wife name", "wife s name"],
    "reg_no": ["registration number", "registration no", "reg no", "reg number", "registration no of death", "certificate number",
               "certificate no"],
    "reg_date": ["registration date", "date of registration", "date of reg", "reg date"],
    "unit": ["registration unit name", "registration unit", "name of registration unit", "issuing authority", "registrar unit"],
}
LABEL_OF = {norm(s): key for key, names in SYNONYMS.items() for s in names}
DATE_KEYS = ("dod", "reg_date")


class _Lines(HTMLParser):
    def __init__(self):
        super().__init__()
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag in ("br", "tr", "p", "div", "li", "table", "h1", "h2", "h3", "h4", "h5", "h6", "dt", "dd", "section"):
            self.out.append("\n")
        elif tag in ("td", "th"):
            self.out.append("\t")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def html_lines(html):
    """HTML to text, one table row per line with its cells separated by a tab (html_text elsewhere flattens the tabs)."""
    p = _Lines()
    p.feed(html)
    lines = []
    for raw in "".join(p.out).split("\n"):
        cells = [re.sub(r"\s+", " ", c).strip() for c in raw.split("\t")]
        line = "\t".join(c for c in cells if c)
        if line:
            lines.append(line)
    return "\n".join(lines)


def _label(line):
    return LABEL_OF.get(norm(line.rstrip(": ")))


def _clean(v):
    return re.sub(r"\s+", " ", v).strip(" :-\t")


def pairs(text):
    """[(key, value)] in order of appearance."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        # A / B: label and value together
        m = re.match(r"^(.{2,45}?)\s*(?::|\t)\s*(.+)$", line)
        if m and _label(m.group(1)) and _clean(m.group(2)):
            out.append((_label(m.group(1)), _clean(m.group(2))))
            i += 1
            continue
        key = _label(line.split(":")[0] if re.match(r"^[^:]{2,45}:\s*-?\s*$", line) else line)
        if key:
            # D: run of consecutive labels, then values in the same order
            j = i
            while j < len(lines) and _label(lines[j]) and not re.search(r"[:\t]\s*\S", lines[j]):
                j += 1
            run = j - i
            if run >= 3 and len(lines) - j >= run and not any(_label(l) for l in lines[j:j + run]):
                for k in range(run):
                    out.append((_label(lines[i + k]), _clean(lines[j + k])))
                i = j + run
                continue
            # C: value on the next line
            if i + 1 < len(lines) and not _label(lines[i + 1].split(":")[0]) and not re.match(r"^[^:]{2,45}:\s*-?\s*$", lines[i + 1]):
                out.append((key, _clean(lines[i + 1])))
                i += 2
                continue
        i += 1
    return out


def _date(value):
    d = match.parse_date(value.replace(",", " ").strip())
    if d:
        return d
    found = sorted(decree.dates_in(value))
    return found[0] if found else None


def parse(text):
    fields = {}
    for key, value in pairs(text):
        if not value or key in fields:
            continue
        if key in DATE_KEYS:
            d = _date(value)
            if d:
                fields[key] = d.isoformat()
            continue
        fields[key] = value
    return fields
