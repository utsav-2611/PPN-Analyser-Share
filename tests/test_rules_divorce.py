import unittest

from analyser import remark, rules_divorce as rd
from analyser.load import Request
from tests.test_decree import AGREEMENT, CONTESTED, CRIMINAL, MUTUAL, PAD

INFO = {"Name": "Sunita Devi", "Date of Divorce": "2026-03-05", "Name of Court": "Family Court Faridabad",
        "Whom to Move": "Applicant", "Is Children Also Moved": "Yes", "Want to Add Parent Family": "No"}
FAM = [{"Full Name": "Sunita Devi", "Spouse Name": "Ravi Kumar", "Gender": "Female", "Relation With HOF": "WIFE"},
       {"Full Name": "Ravi Kumar", "Spouse Name": "Sunita Devi", "Gender": "Male", "Relation With HOF": "SELF"}]
PDF = "/nonexistent.pdf"
LONG = PAD * 12


class _Req(Request):
    pdf_path = PDF


def make(info=None, fam=FAM):
    raw = {"request_id": "1", "list_row": {"Request Type": "Divorced", "FamilyID": "F1"},
           "case": {"User Info": {**INFO, **(info or {})}}, "old_family": fam, "new_family": None,
           "ZCRIM Remark (Ajay Singh)": {"Status": "Forwarded", "Action Date": "11-03-2026"}}
    return _Req("marriage", "/nonexistent", raw)


def run(text, info=None, fam=FAM, method="ocr"):
    d = rd.analyse(make(info, fam), text_of=lambda r: (text, {"pages": 4, "method": method}))
    assert remark.valid(d.remark), d.remark
    return d


class Divorce(unittest.TestCase):
    def test_custody_with_mover_and_children_moved_approves(self):
        d = run(CONTESTED)
        self.assertEqual(d.recommendation, "APPROVE", d.analysis)
        self.assertIn("custody of children with the applicant", d.remark)
        self.assertIn("ZCRIM Ajay Singh forwarded on 11 03 2026", d.remark)

    def test_custody_with_other_parent_rejects_child_move(self):
        d = run(CONTESTED.replace("mother, the petitioner", "father, the respondent"))
        self.assertEqual(d.recommendation, "REJECT")
        self.assertIn("Custody mismatch", d.flags)

    def test_children_not_moved_but_custody_with_mover_holds(self):
        d = run(CONTESTED, {"Is Children Also Moved": "No"})
        self.assertEqual(d.recommendation, "HOLD")

    def test_no_children_with_no_move_approves(self):
        d = run(MUTUAL, {"Is Children Also Moved": "No"})
        self.assertEqual(d.recommendation, "APPROVE", d.analysis)
        self.assertIn("no children", d.remark)

    def test_wrong_document_types_reject(self):
        for text in (CRIMINAL + LONG, AGREEMENT + LONG):
            self.assertEqual(run(text).recommendation, "REJECT")

    def test_short_wrong_type_and_unreadable_hold(self):
        self.assertEqual(run("xx yy").recommendation, "HOLD")
        self.assertEqual(run(CRIMINAL[:200]).recommendation, "HOLD")

    def test_parties_not_named(self):
        fam = [{"Full Name": "Geeta Rani", "Spouse Name": "Mohan Lal", "Gender": "Female"}]
        self.assertEqual(run(CONTESTED + LONG, {"Name": "Geeta Rani"}, fam=fam).recommendation, "REJECT")
        self.assertEqual(run(CONTESTED, {"Name": "Geeta Rani"}, fam=fam).recommendation, "HOLD")  # short text: OCR may have failed
        one = run(CONTESTED + LONG, {"Name": "Geeta Rani"}, fam=[{"Full Name": "Geeta Rani", "Spouse Name": "Ravi Kumar", "Gender": "Female"}])
        self.assertEqual(one.recommendation, "HOLD")  # the spouse is named but the applicant is not
        other = run(CONTESTED, fam=[{"Full Name": "Sunita Devi", "Spouse Name": "Mohan Lal", "Gender": "Female"}], info={"Is Children Also Moved": "No"})
        self.assertIn("Spouse not found", other.flags)  # the applicant is named, the spouse is not: a note, not a hold

    def test_unclear_custody_children_stay_approves_but_children_moving_holds(self):
        text = CONTESTED.replace("The custody of the minor child Aarav shall remain with the mother, the petitioner.",
                                 "The custody of the child shall be decided later.")
        d = run(text, {"Is Children Also Moved": "No"})
        self.assertEqual(d.recommendation, "APPROVE", d.analysis)
        self.assertIn("Custody unclear", d.flags)
        self.assertEqual(run(text).recommendation, "HOLD")

    def test_applicant_absent_from_clear_text_without_spouse_rejects(self):
        fam = [{"Full Name": "Geeta Rani", "Spouse Name": "", "Gender": "Female"}]
        big = CONTESTED + PAD * 40
        self.assertEqual(run(big, {"Name": "Geeta Rani"}, fam=fam).recommendation, "REJECT")
        self.assertEqual(run(CONTESTED, {"Name": "Geeta Rani"}, fam=fam).recommendation, "HOLD")

    def test_unknown_spouse_checks_applicant_only(self):
        d = run(CONTESTED, fam=[{"Full Name": "Sunita Devi", "Spouse Name": "", "Gender": "Female"}])
        self.assertIn("Spouse unknown", d.flags)

    def test_custody_not_mentioned_with_children_not_moved(self):
        text = CONTESTED.replace("The custody of the minor child Aarav shall remain with the mother, the petitioner.", "")
        d = run(text, {"Is Children Also Moved": "No"})
        self.assertEqual(d.recommendation, "APPROVE", d.analysis)
        self.assertIn("not mentioned", d.remark)

    def test_no_document_holds(self):
        req = make()
        req.__class__ = Request  # no pdf_path
        self.assertEqual(rd.analyse(req).recommendation, "HOLD")


if __name__ == "__main__":
    unittest.main()
