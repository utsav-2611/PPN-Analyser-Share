import unittest

from analyser import reasons, run


class Reasons(unittest.TestCase):
    def test_every_pick_is_a_portal_option(self):
        for module, rules in reasons._RULES.items():
            for _, reason in rules:
                self.assertIn(reason, reasons.OPTIONS[module])

    def test_examples(self):
        self.assertEqual(reasons.pick("marital", ["Fake QR"]), reasons.F)
        self.assertEqual(reasons.pick("marriage", ["Name mismatch", "QR text only"]), reasons.X)
        self.assertEqual(reasons.pick("dob", "DOB differs from document"), reasons.B)
        self.assertEqual(reasons.pick("dob", ["Something new"]), reasons.U)

    def test_backfill_fills_reject_and_hold_only(self):
        data = {"requests": {"a": {"module": "dob", "recommendation": "REJECT", "notes": "No document"},
                             "b": {"module": "dob", "recommendation": "APPROVE", "notes": ""}}}
        self.assertEqual(run.backfill_reasons(data), 1)
        self.assertEqual(data["requests"]["a"]["rejectReason"], reasons.V)
        self.assertNotIn("rejectReason", data["requests"]["b"])


if __name__ == "__main__":
    unittest.main()
