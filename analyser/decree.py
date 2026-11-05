"""Reading a divorce decree from its text.  Pure functions on strings (OCR text comes from ocr.py).

  classify(text)            -> (kind, signals)        kind: decree | criminal | agreement | appeal | notice | order_only | not_divorce | unreadable | unknown
  find_party(name, text)    -> (rank, role, pos)      rank exact|close|partial|none|missing; role petitioner|respondent|''
  custody(text)             -> {"state", "who", "excerpt"}
  dates_in(text)            -> set of date objects
  script(text)              -> "latin" | "devanagari" | "mixed" | "none"

OCR of scans is imperfect, so every function returns categories the rules can treat with care instead of guessing.
"""
import re
from datetime import date

from . import match

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
PETITIONER = r"petitioners?|plaintiffs?|appellants?|याची|याचिकाकर्ता|प्रार्थी|वादी|अपीलार्थी"
RESPONDENT = r"respondents?|defendants?|opposite\s+part(?:y|ies)|प्रतिवादी|प्रत्यर्थी|अनावेदक|विपक्षी|प्रतिपक्षी"
RELATION_BEFORE = re.compile(r"(?:w/o|s/o|d/o|c/o|wife\s+of|son\s+of|daughter\s+of|husband\s+of|father\s+of|mother\s+of|पुत्र|पुत्री|पत्नी|पति|पिता)\W*(?:(?:shri|smt|sh|mr|mrs|late)\W+)?$")
ROLE_RE = re.compile(rf"\b(?P<p>{PETITIONER})\b|\b(?P<r>{RESPONDENT})\b", re.I)
NUM_AFTER = re.compile(r"\s*(?:no\.?|number|\(|-|:)?\s*([12])\b")
ORDINAL_BEFORE = re.compile(r"(1st|first|2nd|second)\W*$")


def _norm(text):
    return re.sub(r"[ \t\r\f\v]+", " ", str(text or "")).lower()


def script(text):
    lat = len(re.findall(r"[A-Za-z]", text or ""))
    dev = len(re.findall(r"[ऀ-ॿ]", text or ""))
    if lat + dev < 40:
        return "none"
    if dev > 3 * lat:
        return "devanagari"
    return "latin" if lat > 3 * dev else "mixed"


def word_count(text):
    return len(re.findall(r"[A-Za-zऀ-ॿ]{3,}", text or ""))


# ---- document type -------------------------------------------------------------------------------
GRANT = [
    r"decree\s+of\s+divorce", r"decree\s+for\s+divorce", r"divorce\s+decree", r"decree\s+of\s+dissolution",
    r"marriage\b[^.]{0,120}\b(?:is|stands|be|shall\s+stand)\s+(?:hereby\s+)?dissolved",
    r"dissolv\w+\s+(?:of\s+)?(?:the\s+)?marriage", r"dissolution\s+of\s+(?:the\s+)?marriage",
    r"divorce\b[^.]{0,80}\b(?:is|be|stands)\s+(?:hereby\s+)?(?:granted|allowed)",
    r"petition\b[^.]{0,80}\b(?:is|stands)\s+(?:hereby\s+)?(?:allowed|decreed|granted)",
    r"तलाक\s+की\s+डिक्री", r"विवाह\s+विच्छेद", r"तलाक़?\s+की\s+डिग्री", r"विवाह\s+विघटन", r"डिक्री\s+पारित",
]
MARRIAGE_ACT = r"hindu\s+marriage\s+act|special\s+marriage\s+act|section\s*13|sec\.?\s*13|(?<![\d/.\-])13\s*-?\s*b(?![a-z])|हिन्दू\s+विवाह\s+अधिनियम|हिंदू\s+विवाह\s+अधिनियम"
COURT = r"family\s+court|district\s+(?:and\s+sessions\s+)?judge|court\s+of|principal\s+judge|additional\s+district|high\s+court|न्यायालय|कुटुम्ब|परिवार\s+न्यायालय"
CRIMINAL = [r"\bipc\b", r"indian\s+penal\s+code", r"cr\.?\s?p\.?\s?c", r"bharatiya\s+nyaya", r"\bfir\b", r"\baccused\b", r"acquit",
            r"\bconvict", r"criminal\s+(?:case|complaint|appeal|revision)", r"state\s+(?:vs|v\.|versus)", r"section\s*498", r"\bsection\s*125\b",
            r"सत्र\s+न्यायालय", r"आरोपी", r"दोषमुक्त", r"भा\.?द\.?वि"]
AGREEMENT = [r"agreement", r"compromise\s+deed", r"settlement\s+deed", r"memorandum\s+of\s+(?:understanding|settlement)", r"\bnotary\b",
             r"stamp\s+paper", r"witnesseth", r"first\s+party", r"second\s+party", r"affidavit", r"समझौता", r"शपथ\s*पत्र", r"नोटरी"]
APPEAL = [r"\bappeal\b", r"\bappellant", r"\brevision\b", r"अपील", r"अपीलार्थी"]
NOTICE = [r"legal\s+notice", r"\bnotice\s+under", r"\bsummons?\b", r"\bwarrant\b", r"नोटिस", r"समन"]
ORDER_ONLY = [r"adjourned", r"next\s+date", r"case\s+called", r"put\s+up\s+(?:on|for)", r"fixed\s+for", r"अगली\s+तारीख", r"पेशी"]


def _hits(patterns, text):
    return [p for p in patterns if re.search(p, text, re.I)]


def classify(text):
    """Document type.  A decree needs a grant phrase, the court heading and a marriage act or 'divorce' context."""
    t = _norm(text)
    signals = {"words": word_count(t), "script": script(text)}
    if signals["words"] < 60:
        return "unreadable", signals
    grant, act, court = _hits(GRANT, t), re.search(MARRIAGE_ACT, t, re.I), re.search(COURT, t, re.I)
    crim, agr, app, note, order = (_hits(p, t) for p in (CRIMINAL, AGREEMENT, APPEAL, NOTICE, ORDER_ONLY))
    signals.update(grant=len(grant), act=bool(act), court=bool(court), criminal=len(crim), agreement=len(agr),
                   appeal=len(app), notice=len(note), order_only=len(order))
    head = t[:800]
    if grant and court and (act or "divorce" in t or "तलाक" in t):
        # a criminal judgement or an appeal can quote a decree: they win when the heading says so
        if len(crim) >= 3 and not act:
            return "criminal", signals
        if re.search(r"\bappeal\b|\brevision\s+no|अपील", head, re.I) and not re.search(r"decree\s+sheet|judgment\s+and\s+decree", head, re.I):
            return "appeal", signals
        return "decree", signals
    if not grant and court and act and re.search(r"dissol", t) and re.search(r"decree", t) and len(crim) < 2 and len(agr) < 2:
        return "decree", signals  # wording outside my grant phrases, but court + marriage act + 'dissolved' + 'decree'
    if len(crim) >= 2 and not grant:
        return "criminal", signals
    if not re.search(r"divorce|dissol|decree|तलाक|विवाह\s+विच्छेद|डिक्री", t) and signals["words"] >= 300:
        return "not_divorce", signals  # a long court paper that never mentions divorce, dissolution or a decree
    if len(agr) >= 2 and not court:
        return "agreement", signals
    if len(agr) >= 2 and not grant:
        return "agreement", signals
    if app and re.search(r"\bappeal\b|अपील", head, re.I):
        return "appeal", signals
    if note and not grant:
        return "notice", signals
    if order and not grant:
        return "order_only", signals
    return "unknown", signals


# ---- parties ------------------------------------------------------------------------------------
def _tokens(text):
    """[(word, start, end)] of latin words with titles removed (so 'Smt. Sita Devi' becomes sita devi)."""
    out = []
    for m in re.finditer(r"[a-z0-9]+", text.lower()):
        if m.group() not in match.TITLES:
            out.append((m.group(), m.start(), m.end()))
    return out


def find_party(name, text):
    """Best occurrence of `name` in the text: (rank, role, position).  rank is match.name_match on a word window."""
    nt = match.tokens(name)
    if not nt:
        return "missing", "", -1
    toks = _tokens(text)
    n, best = len(nt), ("none", -1, -1)
    order = {"none": 0, "partial": 1, "close": 2, "exact": 3}
    for i, (w, _, _) in enumerate(toks):
        if not any(match._same_word(w, x) for x in nt):
            continue
        if RELATION_BEFORE.search(text[max(0, toks[i][1] - 24):toks[i][1]].lower()):
            continue  # 'Sita w/o RAVI': the name belongs to a relative, not to the party being described
        for length in {n, n + 1}:
            window = toks[i:i + length]
            if len(window) < min(n, 1):
                continue
            rank = match.name_match(name, " ".join(x[0] for x in window))
            if order.get(rank, 0) > order[best[0]]:
                best = (rank, window[0][1], window[-1][2])
            if rank == "exact":
                break
        if best[0] == "exact":
            break
    if best[0] == "none":
        return "none", "", -1
    return best[0], role_near(text, best[1], best[2]), best[1]


def _label(low, m):
    base = "petitioner" if m.group("p") else "respondent"
    after = NUM_AFTER.match(low, m.end())
    if after:
        return f"{base} {after.group(1)}"
    before = ORDINAL_BEFORE.search(low[max(0, m.start() - 12):m.start()])
    if before:
        return f"{base} {'1' if before.group(1) in ('1st', 'first') else '2'}"
    return base


def role_near(text, start, end):
    """Role label after the name (cause title 'X ... Petitioner No.1 Vs Y ... Respondent'), else just before it.
    Returns 'petitioner', 'petitioner 1', 'respondent 2', ... or ''."""
    low = text.lower()
    m = ROLE_RE.search(low, end, min(len(low), end + 180))
    if not m:
        for cand in ROLE_RE.finditer(low, max(0, start - 60), start):
            m = cand
    return _label(low, m) if m else ""


def petition_kind(text):
    """'mutual' for a joint petition (both spouses petitioners, section 13B), else 'contested' or ''."""
    t = _norm(text)
    if re.search(r"(?<![\d/.\-])13\s*-?\s*\(?b\)?(?![a-z])|mutual\s+consent|आपसी\s+सहमति|संयुक्त\s+याचिका|joint\s+petition", t):
        return "mutual"
    if re.search(MARRIAGE_ACT, t):
        return "contested"
    return ""


# ---- custody ------------------------------------------------------------------------------------
CUSTODY_KEYS = r"custody|custodian|guardianship|visitation|अभिरक्षा|कस्टडी|संरक्षण|अभिभावक"
CHILD_KEYS = r"child(?:ren)?|minor|\bsons?\b|daughters?|बच्च[ेा]|संतान|बेटा|बेटी|पुत्र|पुत्री"
NO_CHILD = r"no\s+(?:child|children|issue)|not\s+blessed|without\s+(?:any\s+)?(?:child|issue)|childless|no\s+child\s+(?:was|were)\s+born|कोई\s+(?:बच्चा|संतान)\s+नहीं|संतान\s+नहीं"
MOTHER = r"\bmother\b|\bwife\b|माता|मां|माँ|पत्नी"
FATHER = r"\bfather\b|\bhusband\b|पिता|पति"
JOINT = r"joint(?:ly)?\s+custody|shared\s+custody|both\s+(?:the\s+)?parents|access\s+to|visit(?:ation)?\s+rights|मुलाकात"


def custody(text):
    """What the decree says on custody of children.

    state: 'no children' | 'stated' | 'unclear' | 'children mentioned' | 'not mentioned'
    who:   'mother' | 'father' | 'petitioner [1|2]' | 'respondent [1|2]' | 'both' | ''     (only when state is 'stated')
    excerpt: up to 300 characters around the custody wording, for the result card
    """
    t = re.sub(r"\s+", " ", _norm(text))
    sentences = re.split(r"(?<=[.;])\s+|\s{2,}", t)
    hits = [s for s in sentences if re.search(CUSTODY_KEYS, s, re.I) and re.search(CHILD_KEYS + "|" + CUSTODY_KEYS, s, re.I)]
    if re.search(NO_CHILD, t) and not hits:
        return {"state": "no children", "who": "", "excerpt": _excerpt(t, NO_CHILD)}
    if not hits:
        state = "children mentioned" if re.search(CHILD_KEYS, t) else "not mentioned"
        return {"state": state, "who": "", "excerpt": _excerpt(t, CHILD_KEYS) if state == "children mentioned" else ""}
    block = " ".join(hits)
    excerpt = block[:300]
    if re.search(JOINT, block) and re.search(MOTHER, block) and re.search(FATHER, block):
        return {"state": "stated", "who": "both", "excerpt": excerpt}
    who = set()
    for s in hits:
        if re.search(MOTHER, s) and not re.search(FATHER, s):
            who.add("mother")
        elif re.search(FATHER, s) and not re.search(MOTHER, s):
            who.add("father")
        else:
            labels = {_label(s, m) for m in ROLE_RE.finditer(s)}
            if len(labels) == 1:
                who.add(labels.pop())
    if len(who) == 1:
        return {"state": "stated", "who": who.pop(), "excerpt": excerpt}
    return {"state": "unclear", "who": "", "excerpt": excerpt}


def _excerpt(t, pattern):
    m = re.search(pattern, t, re.I)
    return t[max(0, m.start() - 100):m.end() + 200] if m else ""


# ---- dates --------------------------------------------------------------------------------------
def dates_in(text):
    out = set()
    t = str(text or "")
    for m in re.finditer(r"\b(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{4})\b", t):
        d = match.parse_date(f"{m.group(1)}/{m.group(2)}/{m.group(3)}")
        if d:
            out.add(d)
    for m in re.finditer(r"\b(\d{1,2})(?:st|nd|rd|th)?[\s,]+(?:of\s+)?([A-Za-z]{3,9})\.?,?\s+(\d{4})\b", t):
        mo = MONTHS.get(m.group(2)[:3].lower())
        if mo:
            try:
                out.add(date(int(m.group(3)), mo, int(m.group(1))))
            except ValueError:
                pass
    for m in re.finditer(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", t):
        mo = MONTHS.get(m.group(1)[:3].lower())
        if mo:
            try:
                out.add(date(int(m.group(3)), mo, int(m.group(2))))
            except ValueError:
                pass
    return out


def court_found(court_name, text):
    """True when the request's court name appears in the text (any two significant words, or one when only one)."""
    words = [w for w in match.tokens(court_name) if len(w) >= 4 and w not in ("court", "district", "judge", "family", "additional", "principal")]
    if not words:
        return None
    low = text.lower()
    need = 1 if len(words) < 2 else 2
    return sum(1 for w in words if w in low) >= need


def resolve_custody(cu, roles, genders):
    """Turn the decree's wording into 'applicant' | 'spouse' | 'both' | 'unresolved' | '' (nothing stated).

    roles:   {'applicant': 'petitioner 1', 'spouse': 'petitioner 2'}  as returned by find_party (may be '')
    genders: {'applicant': 'f'|'m'|'', 'spouse': ...}
    """
    if cu["state"] != "stated":
        return ""
    who = cu["who"]
    if who == "both":
        return "both"
    if who in ("mother", "father"):
        want = "f" if who == "mother" else "m"
        a, sp = genders.get("applicant"), genders.get("spouse")
        if a == want and sp != want:
            return "applicant"
        if sp == want and a != want:
            return "spouse"
        if a and not sp:
            return "applicant" if a == want else "spouse"
        return "unresolved"
    ra, rs = roles.get("applicant", ""), roles.get("spouse", "")
    if who in (ra, rs) and ra != rs:
        return "applicant" if who == ra else "spouse"
    base = who.split()[0]
    sides = [side for side, r in (("applicant", ra), ("spouse", rs)) if r.split()[:1] == [base]]
    if len(sides) == 1 and not (who.split()[1:] and any(r == who for r in (ra, rs))):
        return sides[0] if len(who.split()) == 1 else "unresolved"
    return "unresolved"
