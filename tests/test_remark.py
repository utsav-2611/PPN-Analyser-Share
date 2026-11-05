import unittest

from analyser import remark
from analyser.load import Request


def req(subs):
    raw = {"request_id": "1", "list_row": {}, "case": {}}
    for role, name, status, when in subs:
        raw[f"{role} Remark ({name})"] = {"Status": status, "Remarks": "x", "Action Date": when}
    return Request("marital", "/nonexistent", raw)


class Remark(unittest.TestCase):
    def test_clean(self):
        self.assertEqual(remark.clean("Reg. No: 59/2026 (Ballabgarh), S/o  Ram"), "Reg No 59 2026 Ballabgarh S o Ram")
        self.assertEqual(remark.clean("राम Kumar"), "Kumar")

    def test_subordinate_basis(self):
        r = req([("ZCRIM", "Ajay Singh", "Forwarded", "11-03-2026 10:00"), ("DCRIM", "Bhudev Singh", "Recommended", "17/10/2026")])
        t = remark.build("Approved", "Death certificate verified", r)
        self.assertIn("ZCRIM Ajay Singh forwarded on 11 03 2026", t)
        self.assertIn("DCRIM Bhudev Singh recommended on 17 10 2026", t)
        self.assertTrue(remark.valid(t))

    def test_shortens_subordinate_first(self):
        r = req([("ZCRIM", "Ajay Singh", "Forwarded", "11-03-2026"), ("DCRIM", "Bhudev Singh", "Recommended", "17-10-2026")])
        body = "x" * 10 + " " + " ".join(["word"] * 60)   # about 310 characters, leaves room for the note
        t = remark.build("Rejected", body, r)
        self.assertLessEqual(len(t), 500)
        self.assertIn("ZCRIM", t)            # subordinate kept in a shorter form
        self.assertTrue(remark.valid(t))

    def test_cuts_body_at_word_boundary(self):
        t = remark.build("Rejected", " ".join(["abcdefgh"] * 100), None, parts=[])
        self.assertLessEqual(len(t), 500)
        self.assertTrue(t.endswith(remark.REJECT_NOTE))
        self.assertIn("abcdefgh Applicant may", t)
        self.assertTrue(remark.valid(t))

    def test_rejection_asks_applicant_to_come_with_original(self):
        self.assertTrue(remark.build("Rejected", "date differs", None, parts=[]).endswith(remark.REJECT_NOTE))
        self.assertNotIn("physical", remark.build("Approved", "date matches", None, parts=[]))
        self.assertNotIn("physical", remark.build("On hold", "date differs", None, parts=[]))

    def test_no_subordinates(self):
        self.assertEqual(remark.build("On hold", "date differs", None, parts=[]), "On hold date differs")


class Alternatives(unittest.TestCase):
    def dob_req(self):
        raw = {"request_id": "1", "list_row": {}, "case": {"User Info": {
            "Uploaded Document": "Matriculation certificate", "DOB In PPP": "01-01-1990", "Requested DOB": "08-03-2004"}}}
        return Request("dob", "/nonexistent", raw)

    def dec(self, rec, body):
        from analyser.rules_marriage import Decision
        verdict = {"APPROVE": "Approved", "REJECT": "Rejected", "HOLD": "On hold"}[rec]
        return Decision(rec, remark.build(verdict, body), body=body)

    def test_hold_gives_both_remarks_with_the_finding_as_reject_reason(self):
        out = remark.alternatives(self.dec("HOLD", "Requested DOB 08 03 2004 not found in Matriculation certificate text so officer to read the document"), self.dob_req())
        self.assertTrue(out["APPROVE"].startswith("Approved Matriculation certificate uploaded for change of DOB from 01 01 1990 to 08 03 2004"))
        self.assertTrue(out["REJECT"].startswith("Rejected Matriculation certificate"))
        self.assertIn("not found in Matriculation certificate text Applicant to apply again", out["REJECT"])
        self.assertNotIn("officer to read", out["REJECT"])
        for text in out.values():
            self.assertTrue(remark.valid(text), text)

    def test_own_verdict_keeps_its_remark(self):
        d = self.dec("APPROVE", "Birth record verified")
        out = remark.alternatives(d, self.dob_req())
        self.assertEqual(out["APPROVE"], d.remark)
        self.assertIn("not accepted on examination", out["REJECT"])
        d = self.dec("REJECT", "EPIC not in roll")
        out = remark.alternatives(d, self.dob_req())
        self.assertEqual(out["REJECT"], d.remark)
        self.assertIn("found in order", out["APPROVE"])


if __name__ == "__main__":
    unittest.main()
