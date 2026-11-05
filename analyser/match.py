"""Name, date and age comparison for the rules. Pure functions, no I/O."""
import re
from datetime import date, timedelta
from difflib import SequenceMatcher

TITLES = {"late", "smt", "shrimati", "shri", "sh", "mr", "mrs", "ms", "miss", "dr", "kumari", "km",
          "sri", "shree", "mst", "master", "wd", "so", "do", "wo", "s", "d", "w", "o", "of", "alias"}
# 'S/O', 'D/O', 'W/O' collapse to s o, d o, w o after punctuation is removed: handled by TITLES.


def tokens(name):
    t = re.sub(r"[^a-z0-9 ]", " ", str(name or "").lower())
    return [w for w in t.split() if w not in TITLES]


def phonetic(word):
    """Rough key so common spelling variants of Indian names compare equal."""
    w = word.lower()
    for a, b in (("ph", "f"), ("w", "v"), ("z", "j"), ("q", "k"), ("x", "ks"), ("ee", "i"), ("oo", "u"),
                 ("aa", "a"), ("ou", "u"), ("ck", "k"), ("sh", "s"), ("th", "t"), ("dh", "d"), ("bh", "b"),
                 ("kh", "k"), ("gh", "g"), ("ch", "c")):
        w = w.replace(a, b)
    w = re.sub(r"(.)\1+", r"\1", w)
    if len(w) > 3:
        w = re.sub(r"(?<=[^aeiou])h", "", w)
        w = re.sub(r"[aeiouy]+$", "", w) or w
    return w


def _same_word(a, b):
    if a == b or phonetic(a) == phonetic(b):
        return True
    if len(a) == 1 or len(b) == 1:  # initial
        return a[0] == b[0]
    pa, pb = phonetic(a), phonetic(b)
    return len(pa) > 3 and SequenceMatcher(None, pa, pb).ratio() >= 0.85


def _near_surname(a, b):
    pa, pb = phonetic(a), phonetic(b)
    return len(pa) > 3 and SequenceMatcher(None, pa, pb).ratio() >= 0.8


def name_match(a, b):
    """Compare two person names. Returns 'exact' | 'close' | 'partial' | 'none' | 'missing'.

    exact    same words ignoring case, order, titles, S/O style words
    close    same words after spelling-variant tolerance (Mohammed/Mohamad, Rajinder/Rajender)
    partial  every word of the shorter name is in the longer (a middle or surname is missing)
    """
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return "missing"
    if sorted(ta) == sorted(tb):
        return "exact"
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)

    def covered(words, pool):
        pool = list(pool)
        for w in words:
            hit = next((p for p in pool if _same_word(w, p)), None)
            if hit is None:
                return False
            pool.remove(hit)
        return True

    initials = any(len(w) == 1 for w in ta + tb)
    if len(ta) == len(tb) and not initials and covered(ta, tb):
        return "close"
    if len(ta) == len(tb) > 1 and not initials and all(_same_word(x, y) for x, y in zip(ta[:-1], tb[:-1])) and _near_surname(ta[-1], tb[-1]):
        return "close"  # same given names, surname spelled slightly differently (one letter)
    if covered(short, long_):
        return "partial"
    return "none"


def one_letter_variant(a, b):
    """Same number of words, every word the same except exactly one that is a near spelling (phonetic similarity >= 0.8).
    Weaker than name_match: use it only when other facts (such as the date of death) already identify the person."""
    ta, tb = tokens(a), tokens(b)
    if len(ta) != len(tb) or len(ta) < 1 or any(len(w) == 1 for w in ta + tb):
        return False
    odd = [(x, y) for x, y in zip(ta, tb) if not _same_word(x, y)]
    return len(odd) == 1 and len(phonetic(odd[0][0])) > 3 and SequenceMatcher(None, phonetic(odd[0][0]), phonetic(odd[0][1])).ratio() >= 0.8


def acceptable(a, b, allow_partial=True):
    """True when two names are the same person for rule purposes."""
    r = name_match(a, b)
    return r in ("exact", "close") or (allow_partial and r == "partial")


# --- dates -------------------------------------------------------------------------------
def parse_date(text):
    """Accept dd/mm/yyyy, dd-mm-yyyy, dd.mm.yyyy, dd mm yyyy, yyyy-mm-dd. Returns date or None."""
    s = str(text or "").strip()
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ].*)?", s)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.fullmatch(r"(\d{1,2})[/.\- ](\d{1,2})[/.\- ](\d{4})", s)
        if not m:
            return None
        d, mo, y = map(int, m.groups())
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def age_on(dob, on):
    """(years, months) completed on date `on`. Both are date objects."""
    months = (on.year - dob.year) * 12 + (on.month - dob.month) - (1 if on.day < dob.day else 0)
    return months // 12, months % 12


def fmt_date(d):
    """Remark format: 25 10 2025."""
    return f"{d.day:02d} {d.month:02d} {d.year}" if d else ""


def add_months(d, n):
    """Date n months later (n may be negative); the day is clamped to the month length."""
    total = d.year * 12 + (d.month - 1) + n
    y, m = divmod(total, 12)
    m += 1
    for day in (d.day, 30, 29, 28):
        try:
            return date(y, m, min(d.day, day))
        except ValueError:
            continue
    return date(y, m, 28)


def birthday(dob, years):
    """The date on which someone born on `dob` completes `years` years (29 Feb falls on 28 Feb)."""
    try:
        return date(dob.year + years, dob.month, dob.day)
    except ValueError:
        return date(dob.year + years, dob.month, 28)


def dob_range_for_age(age, as_on):
    """Earliest and latest DOB of a person who was `age` completed years old on `as_on` (both inclusive)."""
    latest = _years_before(as_on, age)
    earliest = _years_before(as_on, age + 1) + timedelta(days=1)
    return earliest, latest


def _years_before(d, years):
    try:
        return date(d.year - years, d.month, d.day)
    except ValueError:
        return date(d.year - years, d.month, 28)


def dob_fits_age(dob, age, as_on):
    """True when `dob` is consistent with `age` completed years on `as_on`."""
    lo, hi = dob_range_for_age(age, as_on)
    return lo <= dob <= hi
