"""probe_dob without the document pass (no QR, no OCR): fields, labels, counts and the electoral roll only.

  python -m analyser.probe_dob_quick
Respects CRID_WORK_ROOT and ELECTORS_DB.  Saves to store/probe_dob_quick.txt.
"""
from . import probe_dob

if __name__ == "__main__":
    probe_dob.main(documents=False, out=probe_dob.OUT.with_name("probe_dob_quick.txt"))
