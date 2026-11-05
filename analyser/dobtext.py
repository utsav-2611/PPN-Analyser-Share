"""Find dates of birth in OCR text of identity and school documents.

  dates_in(text)            every date written as 23/03/2005, 23 March 2005, March 23, 2005 or in words
  find_dob(text, target)    'exact' | 'one digit off' | None
  ages_as_on(text)          [(as_on date, age)] from voter card lines such as 'Age as on 1.1.2019 : 35 Years'
Devanagari digits are read as ordinary digits.  Nothing here prints text.
"""
import re
from datetime import date

DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]
_MON3 = "|".join(m[:3] for m in MONTHS)
NUM_DATE = re.compile(r"(?<!\d)(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{4})(?!\d)")
NAME_DATE = re.compile(rf"(?<!\d)(\d{{1,2}})\s*(?:st|nd|rd|th)?[\s,\-]*({_MON3})[a-z]*[\s,\-.]*(\d{{4}}|\d{{2}}\s\d{{2}})(?!\d)", re.I)
WORDDAY_NUMYEAR = re.compile(rf"((?:[a-z]+[\s\-]+){{1,2}})({_MON3})[a-z]*[\s,\-.]*(\d{{4}}|\d{{2}}\s\d{{2}})(?!\d)", re.I)
US_DATE = re.compile(rf"({_MON3})[a-z]*\s+(\d{{1,2}})\s*(?:st|nd|rd|th)?,?\s+(\d{{4}})(?!\d)", re.I)
AGE_AS_ON = re.compile(r"age\s+as\s+on\s*[:\-]?\s*(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{4}).{0,150}?(?<!\d)(\d{1,3})(?!\d)\s*:?\s*years?", re.I | re.S)
PLAIN_AGE = re.compile(r"date\s+of\s+birth\s*(?:/|&|,|and|\w{1,3})?\s*age\s*[:;.\-]?\s*(\d{1,3})(?!\d)", re.I)

_UNITS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen "
    "eighteen nineteen".split())}
_TENS = {w: 10 * (i + 2) for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split())}
_ORD = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9,
        "tenth": 10, "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14, "fifteenth": 15, "sixteenth": 16,
        "seventeenth": 17, "eighteenth": 18, "nineteenth": 19, "twentieth": 20, "thirtieth": 30}


def _small(tokens):
    """0..99 from 1-2 words ('forty', 'five', 'twenty five', 'nineteen'); None if not a number."""
    if len(tokens) == 1:
        t = tokens[0]
        return _UNITS.get(t) if t in _UNITS else _TENS.get(t) if t in _TENS else _ORD.get(t)
    if len(tokens) == 2 and tokens[0] in _TENS:
        u = _UNITS.get(tokens[1]) if tokens[1] in _UNITS else _ORD.get(tokens[1])
        if u is not None and 0 < u < 10:
            return _TENS[tokens[0]] + u
    return None


def _day(tokens):
    d = _small(tokens)
    return d if d and 1 <= d <= 31 else None


def _year(tokens):
    """'two thousand five' / 'two thousand and five' / 'nineteen ninety eight' / 'one thousand nine hundred ninety eight'."""
    t = [w for w in tokens if w != "and"]
    if t[:2] == ["two", "thousand"]:
        rest = t[2:]
        return 2000 + (_small(rest) or 0) if not rest or _small(rest) is not None else None
    if t[:4] == ["one", "thousand", "nine", "hundred"]:
        rest = t[4:]
        return 1900 + (_small(rest) or 0) if not rest or _small(rest) is not None else None
    if t and t[0] == "nineteen" and len(t) >= 2:
        s = _small(t[1:])
        return 1900 + s if s is not None and s >= 10 else None
    return None


def _word_dates(text):
    words = [w for w in re.findall(r"[a-z]+", text.lower()) if w not in ("of", "the")]
    found = set()
    for i, w in enumerate(words):
        if w not in MONTHS:
            continue
        month = MONTHS.index(w) + 1
        day = next((d for k in (2, 1) if i - k >= 0 and (d := _day(words[i - k:i]))), None)
        if day is None:
            continue
        for k in range(8, 1, -1):  # the longest reading of the year wins
            y = _year(words[i + 1:i + 1 + k])
            if y:
                try:
                    found.add(date(y, month, day))
                except ValueError:
                    pass
                break
    return found


def WORDDAY_NUM_YEAR_iter(text):
    """(day, month, year) where the day is in words ('Twelfth Feb 2005'); the day is returned as a number string."""
    for m in WORDDAY_NUMYEAR.finditer(text):
        tokens = [w for w in re.findall(r"[a-z]+", m.group(1).lower()) if w not in ("of", "the")]
        day = next((d for k in (2, 1) if len(tokens) >= k and (d := _day(tokens[-k:]))), None)
        if day:
            yield str(day), m.group(2), m.group(3)


HI_MONTHS = {"जनवरी": "January", "फरवरी": "February", "फ़रवरी": "February", "मार्च": "March", "अप्रैल": "April", "अप्रेल": "April",
             "मई": "May", "जून": "June", "जुलाई": "July", "अगस्त": "August", "सितंबर": "September", "सितम्बर": "September",
             "अक्टूबर": "October", "अक्तूबर": "October", "नवंबर": "November", "नवम्बर": "November", "दिसंबर": "December",
             "दिसम्बर": "December"}
_HI_MONTH = re.compile("|".join(sorted(HI_MONTHS, key=len, reverse=True)))
_SLIP_DATE = re.compile(r"(?<![0-9A-Za-z])([0-9OoIl|SB]{1,2})\s*([/.\-])\s*([0-9OoIl|SB]{1,2})\s*\2\s*([0-9OoIl|SB]{4})(?![0-9A-Za-z])")
_SLIP = str.maketrans("OoIl|SB", "0011158")


def fix_digit_slips(text):
    """OCR often reads digits of a date as letters (O for 0, l or I for 1, S for 5, B for 8).  Correct them inside tokens
    shaped like dd/mm/yyyy only, and only when the token also has a real digit; other text is left alone."""
    def fix(m):
        token = m.group(0)
        return token.translate(_SLIP) if re.search(r"\d", token) else token
    return _SLIP_DATE.sub(fix, text or "")


def dates_in(text):
    text = _HI_MONTH.sub(lambda m: HI_MONTHS[m.group(0)], (text or "").translate(DEV_DIGITS))
    found = set()

    def add(y, m, d):
        try:
            found.add(date(int(y), int(m), int(d)))
        except ValueError:
            pass

    for d, m, y in NUM_DATE.findall(text):
        add(y, m, d)
    for d, mon, y in NAME_DATE.findall(text):
        add(y.replace(" ", ""), [x[:3] for x in MONTHS].index(mon.lower()[:3]) + 1, d)
    for words, mon, y in WORDDAY_NUM_YEAR_iter(text):
        add(y.replace(" ", ""), [x[:3] for x in MONTHS].index(mon.lower()[:3]) + 1, words)
    for mon, d, y in US_DATE.findall(text):
        add(y, [x[:3] for x in MONTHS].index(mon.lower()[:3]) + 1, d)
    return found | _word_dates(text)


def loose_forms(text, target):
    """Ways of writing `target` that dates_in does not read, each needing the whole of the requested date: two digit year
    (08/03/04), and day, month name and year spread over up to four nearby lines.  True when one is found."""
    flat = (text or "").translate(DEV_DIGITS)
    d, m, y = target.day, target.month, target.year
    sep = r"\s*[/.\-]\s*"
    if re.search(rf"(?<!\d)0?{d}{sep}0?{m}{sep}{y % 100:02d}(?!\d)", flat):
        return True
    lines = [x for x in flat.splitlines() if x.strip()]
    for i in range(len(lines)):
        window = " ".join(lines[i:i + 4])
        if (re.search(rf"(?<!\d)0?{d}(?!\d)", window) and re.search(rf"(?<!\d){y}(?!\d)", window)
                and re.search(MONTHS[m - 1][:3], window, re.I)):
            return True
    return False


def find_dob(text, target):
    """'exact' when `target` (a date) is written in the text, 'one digit off' when a date in the text differs from it
    by a single digit of ddmmyyyy (typical OCR slip), else None."""
    if not target:
        return None
    found = dates_in(text)
    if target in found or loose_forms(text, target):
        return "exact"
    fixed = fix_digit_slips(text)
    if fixed != text:
        slipped = dates_in(fixed)
        if target in slipped:
            return "exact"
        found = found | slipped
    want = f"{target.day:02d}{target.month:02d}{target.year}"
    for d in found:
        got = f"{d.day:02d}{d.month:02d}{d.year}"
        if sum(a != b for a, b in zip(want, got)) == 1:
            return "one digit off"
    return None


def ages_as_on(text):
    out = []
    for d, m, y, age in AGE_AS_ON.findall((text or "").translate(DEV_DIGITS)):
        try:
            out.append((date(int(y), int(m), int(d)), int(age)))
        except ValueError:
            pass
    return out


_BIRTH_LINE = re.compile(r"birth|\bdob\b|d\.o\.b|जन्म", re.I)
_NOT_BIRTH_DATE = re.compile(r"issue|dated|printed|registration|वितरण|निर्गत|\bas on\b|\bage\b|\broll\b|\bcard\b", re.I)


def dob_context(text, same_line=False):
    """What the document says on its date-of-birth lines: (full dates, years).

    A DOB line is a line mentioning birth / DOB; the line itself and (unless `same_line`) the next one are read.
    Lines about issue, registration, 'age as on' dates and the card footnote are skipped, so their years are not taken
    as a birth year.  Years are four digit numbers 1930 to 2030 (a date whose day or month is unreadable still gives
    its year).
    """
    lines = (text or "").translate(DEV_DIGITS).splitlines()
    dates, years = set(), set()
    for i, line in enumerate(lines):
        if not _BIRTH_LINE.search(line):
            continue
        chunks = (line,) if same_line else (line, lines[i + 1] if i + 1 < len(lines) else "")
        for chunk in chunks:
            if _NOT_BIRTH_DATE.search(chunk):
                continue
            dates |= dates_in(chunk)
            years |= {int(y) for y in re.findall(r"(?<!\d)(19[3-9]\d|20[0-2]\d|2030)(?!\d)", chunk)}
    return dates, years


def plain_ages(text):
    """Ages written without a date, as in 'Date of Birth / Age : 35' (electoral roll certificates, some voter cards)."""
    return [int(a) for a in PLAIN_AGE.findall((text or "").translate(DEV_DIGITS)) if 10 <= int(a) <= 110]
