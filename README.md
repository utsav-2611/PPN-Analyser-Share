# PPN Analyser

The analyser reads a request that was made on the **PPN (Parivar Pehchan Patra) verification portal** together with the certificate
uploaded for it, checks the certificate, applies the written rules and gives back:

- a **recommendation**: `APPROVE`, `REJECT` or `HOLD` (HOLD means "a person must look", with the reason),
- the **reason** in plain words, the **remark** ready to be entered on the portal, and the portal's **reject reason**.

It runs **locally** (no cloud service, no AI service). It never contacts the portal and never submits anything: it only reads
the request files you give it and writes its results to a local file. The final decision always belongs to a person.

Modules: **DOB Tagging** (voter ID, board and school certificates, School Leaving Certificate, passport, birth certificate,
government ID, electoral roll certificate), **Marital Tagging** (Widow, Widower, Married, Divorced) and
**Marriage / Divorce PPN update**. The rules are in [`docs/RULES.md`](docs/RULES.md).

What it checks, in short: is a document attached and of which type; is it genuine (QR code decoded, the link must be a
government site, the record is opened on the issuing official site and read; voter IDs are looked up in an electoral roll
database); does it match the request (dates, names, parents, family, ages). It cannot judge seals, signatures or paper:
there is no forgery detection.

---

## 1. What you need

| | |
|---|---|
| Computer | A Mac is recommended: photographed certificates are read with Apple Vision (offline). Other systems fall back to tesseract |
| Python | 3.10 or newer |
| Homebrew packages | `zbar` (QR reading), `tesseract` and `tesseract-lang` (Hindi text) |
| Internet | Only to the government site named in a certificate's own QR code (hosts ending `gov.in` or `nic.in`, see [`rules.yaml`](rules.yaml)). Any other QR host is treated as fake and never opened |
| Electoral roll | Optional, needed only for voter ID checks. Your own SQLite database, format in [`data/Electors/README.md`](data/Electors/README.md). Without it, those requests go to HOLD with a message saying so |

## 2. Install

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
brew install zbar tesseract tesseract-lang
cp config.example.yaml config.yaml        # optional, see section 3
.venv/bin/python -m unittest discover -s tests -t .
```

The tests use made-up data only.

## 3. Settings

`config.yaml` (optional, never committed) or environment variables:

| Setting | Environment | Default |
|---|---|---|
| `data_root`: folder that holds your requests | `CRID_WORK_ROOT` | `./data` |
| `electors_db`: the electoral roll database | `ELECTORS_DB` | `<data_root>/Electors/electors.db` |

`PPN_STORE_DIR` moves the results folder (default `./store`).

## 4. Input format: what a request must look like

Put each request in its own folder:

```
<data_root>/
  DOB/               requests/<request id>/
  Marital/           requests/<request id>/
  Marriage-Divorce/  requests/<request id>/
```

and inside every request folder:

| File | |
|---|---|
| `case.json` | **required**. The request as shown on the portal (below) |
| `document.pdf` | the uploaded certificate, all pages. Without it the request is rejected as "No document uploaded" |
| `case_window.png` | optional screenshot of the request; only noted, not analysed |

A complete made-up example is in [`examples/DOB/requests/EXAMPLE-1/`](examples/DOB/requests/EXAMPLE-1/case.json). Use it with
`CRID_WORK_ROOT=$PWD/examples`.

### `case.json`

All values are strings, exactly as the portal shows them. Labels are matched ignoring case, spaces and punctuation, and missing
fields are tolerated (the analyser then holds the request rather than guessing).

```json
{
  "module": "dob",                      "dob" | "marital" | "marriage"   (the folder decides the module)
  "request_id": "12345",                defaults to the folder name
  "tab": "pending",                     "priority" | "pending" | "newRegistration"; "tabs": ["pending"] may list several
  "collected_at": "2026-01-01T10:00:00",
  "list_row":  { ...the request's row in the portal list... },
  "case": {
    "User Info": { ...the fields of the request form... },
    "ZCRIM Remark (<name>)": { "Status": "Forwarded", "Reason": "", "Remarks": "", "Action Date": "02-01-2026 10:00" }
  },
  "family": [ { "Full Name": "", "Father Name": "", "Mother Name": "", "Spouse Name": "",
                "Relation With HOF": "", "Date of Birth": "", "Gender": "" } ]
}
```

- `"ZCRIM Remark (<name>)"`, `"DCRIM Remark (<name>)"` and `"FCP Remark (<name>)"` are the remarks of the earlier levels. They are
  optional; when present, the analyser adds them to the remark as the basis ("ZCRIM <name> forwarded on <date> on basis of uploaded document").
- `family` is the family table of the applicant's family. For **Marriage / Divorce** it is two tables, `old_family` and `new_family`.
- Dates are `dd-mm-yyyy` (other common layouts are read too).

Fields the rules read, by module (everything else is ignored):

| Module | `list_row` | `case["User Info"]` | family table |
|---|---|---|---|
| **DOB** | `FamilyID`, `Name`, `Father Name`, `Dob In PPP`, `Requested DOB`, `Flag` | `Name`, `Father Name`, `Mother Name`, `DOB In PPP`, `Requested DOB`, `Uploaded Document` (the type as labelled on the portal), `Document Number` | `family` (names, parents, dates of birth) |
| **Marital** | `FamilyID`, `Name`, `Current MS PPP`, `Requested MS PPP`, `Flag` | `Name`, `Father Name`, `Mother Name`, `Current Status In PPP`, `Requested Status In PPP` (Widow, Widower, Married, Divorced, Unmarried), `Spouse Full Name`, `Spouse Father Name`, `Date Of Death`, `Death Certificate Number`, `Issuing Authority`, `Date Of Marriage`, `Date of Birth` | `family` |
| **Marriage / Divorce** | `FamilyID`, `Name`, `Request Type` (`Marriage` or `Divorced`), `Flag` | `Old Family ID`, `New Family ID`, `Name`, `Father Name`, `Mother Name`, `Date of Birth`, `Request Type`, `Is Marriage in Haryana`, `Place of Marriage`, `Date Of Marriage`, `Spouse Full Name`; for a divorce also `Date of Divorce`, `Name of Court`, `Is Children Also Moved`, `Whom to Move` | `old_family` and `new_family` |

`Flag` (optional) marks Lado Lakshmi (`LLY`) requests; they get the same checks and are only listed first.

## 5. Run

```bash
.venv/bin/python -m analyser.run                       # analyse requests not analysed yet
.venv/bin/python -m analyser.run --all                 # analyse everything again
.venv/bin/python -m analyser.run --modules dob,marital # only some modules
.venv/bin/python -m analyser.run --workers 4           # several requests at a time
.venv/bin/python -m analyser.run --dry-run             # counts only, nothing is written
.venv/bin/python -m analyser.report                    # counts per module and recommendation
.venv/bin/python -m analyser.report --csv results.csv  # one row per request
```

Answers from official sites are cached in `store/cache`, so a re-run does not contact them again (failed lookups are never
cached). Scanned certificates take a few seconds each, mostly for QR decoding when a document has no QR.

## 6. Output

Results are saved in `store/results.json`, one record per request. The main fields:

| Field | Meaning |
|---|---|
| `recommendation` | `APPROVE`, `REJECT` or `HOLD` |
| `proposedRemark` | the remark for that recommendation: letters, digits and spaces only, at most 500 characters |
| `remarks` | the remark for each of `APPROVE` and `REJECT`, whichever way the person decides |
| `rejectReason` | the portal's reject reason (a fixed list per module) for REJECT and HOLD |
| `analysis`, `notes` | what was found, in words; the flags that decided it |
| `facts`, `verification` | the extracted values; how the certificate was verified and what the official site answered |

| Recommendation | Meaning |
|---|---|
| **APPROVE** | The document was verified (or the QR is a genuine government site that has no checker here) and everything agrees. The remark says what was checked |
| **REJECT** | A rule says reject: fake QR host, certificate of another person, different spouse, under-age marriage, DOB that does not match, no document, voter ID not in the roll, and similar. Every rejected remark ends with a note asking the applicant to come to the ADC office with the original document |
| **HOLD** | The analyser cannot settle it; the reason says what to check. Never a final decision |

## 7. Code map

`analyser/load.py` reads `case.json` · `qr.py` decodes QR codes and checks hosts · `verify/` one module per official site ·
`match.py` names, dates and ages · `ocr.py`, `vision_ocr.py` text from documents · `rules_dob.py`, `rules_marital.py`,
`rules_marriage.py`, `rules_divorce.py` the decisions · `remark.py` builds remarks · `reasons.py` portal reject reasons ·
`store.py` results file · `run.py` the command · `report.py` the summary · `probe_*` developer probes that print masked layouts
(letters `a`, digits `9`) so a document layout can be discussed without exposing it.

## 8. Privacy

Requests, documents, the electoral roll and `store/` (results, OCR text, official-site responses) contain citizen data. They are
git-ignored; never put them in git, issues, chat or screenshots. Tests use made-up data only. Share a masked layout from a
`probe_*` module instead of a real document.

## Licence

[MIT](LICENSE). The software is provided as is, without warranty; decisions made with it remain the responsibility of the person who takes them.
