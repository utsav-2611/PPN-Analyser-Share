"""Portal reject reasons: the dropdown options per module (captured 26 Oct 2026) and the one the analyser suggests."""

M, L, F, I = ("Certificate details and self-declared information do not match", "Certificate is not legible",
              "Document is forged", "Document is incorrect")
U, X, V = "Document is unclear or not acceptable", "Information mismatch", "Invalid document"
A, B, C = ("DOB not available in document", "DOB not matched with document",
           "Document attached is not matching with Document Type")

# The portal's list for each module, in portal order.  "Other" opens a free text field, so it is never suggested.
OPTIONS = {
    "marital": [M, L, F, I, "Other"],
    "marriage": [U, X, V, "Other"],
    "dob": [A, B, C, U, V, "Other"],
}

# (flag text, reason): first match wins on the lower cased flags; the last entry is the module's fallback.
_RULES = {
    "marital": [("fake qr", F), ("qr unreadable", L), ("no qr", L), ("not a death record", I), ("not a decree", I), ("", M)],
    "marriage": [("fake qr", V), ("underage", V), ("child before 18", V), ("not a decree", V), ("not a death record", V),
                 ("qr unreadable", U), ("decree unreadable", U), ("no document", U), ("no qr", U),
                 ("mismatch", X), ("differs", X), ("spouse", X), ("parties", X), ("custody", X), ("not in family", X),
                 ("applicant not found", X), ("name", X), ("date", X), ("deceased", X), ("married in ppp", X), ("", U)],
    "dob": [("fake qr", V), ("certificate not of applicant", V), ("both parents", V), ("father differs", V),
            ("not found in document", A), ("school document type unclear", C),
            ("differs", B), ("one digit", B), ("several dates", B), ("outside voter id", B),
            ("no document", V), ("register copy", V), ("slc", V), ("voter id issued", V), ("epic", V), ("roll entry", V),
            ("", U)],
}


def pick(module, flags):
    """The reject reason to pre-select for a REJECT or HOLD request; flags is a list or the stored '; ' joined notes."""
    text = (flags if isinstance(flags, str) else "; ".join(flags)).lower()
    return next(reason for key, reason in _RULES[module] if key in text)
