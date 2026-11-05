import unittest
from datetime import date

from analyser import decree as d

PAD = " The court heard learned counsel for the parties and perused the record carefully. " * 4

CONTESTED = ("IN THE COURT OF PRINCIPAL JUDGE FAMILY COURT FARIDABAD HMA Petition No 12 of 2025 "
             "Smt. Sunita Devi w/o Ravi Kumar ... Petitioner Versus Ravi Kumar s/o Mohan Lal ... Respondent. " + PAD +
             "The petition under Section 13 of the Hindu Marriage Act is allowed and the marriage solemnized between the parties on "
             "12.02.2015 is hereby dissolved by a decree of divorce. The custody of the minor child Aarav shall remain with the "
             "mother, the petitioner. Pronounced on 05 March 2026.")
MUTUAL = ("IN THE COURT OF DISTRICT JUDGE Petition under Section 13-B Hindu Marriage Act Ravi Kumar ... Petitioner No.1 "
          "and Sunita Devi ... Petitioner No.2. " + PAD +
          "By mutual consent the marriage is dissolved. Decree of divorce be drawn up. The parties are not blessed with any child. Dated 5/3/2026")
CRIMINAL = ("IN THE COURT OF SESSIONS JUDGE State vs Ravi Kumar FIR No 44 under Section 498A IPC. The accused is acquitted. "
            "Criminal case dismissed, convicted none. " + PAD)
AGREEMENT = ("AGREEMENT ON STAMP PAPER notarised by notary. This agreement is made between first party Ravi and second party Sunita "
             "witnesseth that the parties agree to live separately. Affidavit attached. " + PAD)
APPEAL = ("IN THE HIGH COURT First Appeal No 33 of 2026 Appellant Ravi Kumar versus Respondent Sunita Devi. The appeal is listed. "
          "Divorce marriage act hindu appeal pending. " + PAD)
NOTICE = ("LEGAL NOTICE under Section 80 sent by advocate. Notice is given to Ravi Kumar to respond within thirty days. " + PAD)
ORDER = ("IN THE COURT OF CIVIL JUDGE Case called. Counsel absent. The case is adjourned and put up for next date. " + PAD)


class Classify(unittest.TestCase):
    def test_kinds(self):
        for text, kind in ((CONTESTED, "decree"), (MUTUAL, "decree"), (CRIMINAL, "criminal"), (AGREEMENT, "agreement"),
                           (APPEAL, "appeal"), (NOTICE, "notice"), (ORDER, "order_only")):
            self.assertEqual(d.classify(text)[0], kind, kind)

    def test_long_court_paper_without_divorce_words(self):
        t = "IN THE COURT OF CIVIL JUDGE Petition filed by the petitioner. Annexure A attached. " + PAD * 12
        self.assertEqual(d.classify(t)[0], "not_divorce")
        self.assertEqual(d.classify(t[:300] + " divorce")[0] == "not_divorce", False)

    def test_appeal_in_heading_is_not_a_decree(self):
        t = CONTESTED.replace("HMA Petition No 12 of 2025", "Appeal against order No 12 of 2025")
        self.assertEqual(d.classify(t)[0], "appeal")
        self.assertEqual(d.classify(CONTESTED)[0], "decree")  # 'appeal' further down the text does not matter
        self.assertEqual(d.classify(CONTESTED + PAD * 12 + " No appeal lies. ")[0], "decree")

    def test_decree_without_my_grant_phrase(self):
        t = ("IN THE COURT OF DISTRICT JUDGE Hindu Marriage Act. Judgment: the parties wish to part. Marriage between them stands dissolved "
             "hereafter. Let a decree be drawn. " + PAD * 12).replace("stands dissolved", "has been dissolved")
        self.assertEqual(d.classify(t)[0], "decree")

    def test_unreadable(self):
        self.assertEqual(d.classify("xx yy z q")[0], "unreadable")

    def test_hindi_decree(self):
        t = "परिवार न्यायालय फरीदाबाद हिन्दू विवाह अधिनियम धारा 13 याचिका स्वीकार की जाती है। विवाह विच्छेद की डिक्री पारित। " * 8
        self.assertEqual(d.classify(t)[0], "decree")
        self.assertEqual(d.script(t), "devanagari")


class Parties(unittest.TestCase):
    def test_roles(self):
        self.assertEqual(d.find_party("Sunita Devi", CONTESTED)[:2], ("exact", "petitioner"))
        # the husband's name after 'w/o' must not take the wife's role; his own entry is the respondent
        self.assertEqual(d.find_party("Ravi Kumar", CONTESTED)[:2], ("exact", "respondent"))

    def test_respondent_role(self):
        text = "Sunita Devi ... Petitioner Versus Ravi Kumar son of Mohan ... Respondent. " + PAD
        self.assertEqual(d.find_party("Ravi Kumar", text)[:2], ("exact", "respondent"))

    def test_spelling_and_absent(self):
        self.assertEqual(d.find_party("Sunitha Devi", CONTESTED)[0], "close")
        self.assertEqual(d.find_party("Geeta Rani", CONTESTED)[0], "none")
        self.assertEqual(d.find_party("", CONTESTED)[0], "missing")

    def test_petition_kind(self):
        self.assertEqual(d.petition_kind(MUTUAL), "mutual")
        self.assertEqual(d.petition_kind(CONTESTED), "contested")


class Custody(unittest.TestCase):
    def test_mother(self):
        c = d.custody(CONTESTED)
        self.assertEqual((c["state"], c["who"]), ("stated", "mother"))
        self.assertIn("custody", c["excerpt"])

    def test_father_and_role(self):
        self.assertEqual(d.custody("Custody of the child is given to the father. " + PAD)["who"], "father")
        self.assertEqual(d.custody("The respondent shall have custody of the minor son. " + PAD)["who"], "respondent")

    def test_no_children_and_not_mentioned(self):
        self.assertEqual(d.custody(MUTUAL)["state"], "no children")
        self.assertEqual(d.custody("Marriage dissolved. " + PAD)["state"], "not mentioned")
        self.assertEqual(d.custody("The parties have a daughter born in 2016. " + PAD)["state"], "children mentioned")

    def test_both_and_unclear(self):
        t = "Joint custody of the child with the mother and the father with visitation rights. "
        self.assertEqual(d.custody(t)["who"], "both")
        self.assertEqual(d.custody("The custody of the child shall be decided later. ")["state"], "unclear")


class Resolve(unittest.TestCase):
    G = {"applicant": "f", "spouse": "m"}

    def test_by_gender(self):
        self.assertEqual(d.resolve_custody({"state": "stated", "who": "mother"}, {}, self.G), "applicant")
        self.assertEqual(d.resolve_custody({"state": "stated", "who": "father"}, {}, self.G), "spouse")
        self.assertEqual(d.resolve_custody({"state": "stated", "who": "mother"}, {}, {}), "unresolved")

    def test_by_numbered_role(self):
        roles = {"applicant": "petitioner 1", "spouse": "petitioner 2"}
        self.assertEqual(d.resolve_custody({"state": "stated", "who": "petitioner 2"}, roles, self.G), "spouse")
        self.assertEqual(d.resolve_custody({"state": "stated", "who": "petitioner"}, roles, self.G), "unresolved")

    def test_by_plain_role(self):
        roles = {"applicant": "respondent", "spouse": "petitioner"}
        self.assertEqual(d.resolve_custody({"state": "stated", "who": "petitioner"}, roles, self.G), "spouse")

    def test_nothing_stated(self):
        self.assertEqual(d.resolve_custody({"state": "no children", "who": ""}, {}, self.G), "")


class NumberedRoles(unittest.TestCase):
    def test_numbers_from_title(self):
        t = "Sunita Devi ... Petitioner No.1 and Ravi Kumar ... Petitioner No.2. " + PAD
        self.assertEqual(d.find_party("Sunita Devi", t)[1], "petitioner 1")
        self.assertEqual(d.find_party("Ravi Kumar", t)[1], "petitioner 2")

    def test_custody_label_with_number(self):
        c = d.custody("Custody of the minor child shall remain with petitioner no.2. " + PAD)
        self.assertEqual(c["who"], "petitioner 2")

    def test_13b_not_confused_with_year(self):
        self.assertEqual(d.petition_kind("Hindu Marriage Act. Married on 12.02.2013 by rites. " + PAD), "contested")
        self.assertEqual(d.petition_kind("petition under section 13-B of the Hindu Marriage Act"), "mutual")
        self.assertEqual(d.petition_kind("petition under section 13(1) of the Hindu Marriage Act in 2013 by the court"), "contested")


class Dates(unittest.TestCase):
    def test_formats(self):
        got = d.dates_in("on 12.02.2015, 5/3/2026, 05 March 2026, 7th Feb, 2024 and March 9, 2025")
        self.assertEqual(got, {date(2015, 2, 12), date(2026, 3, 5), date(2024, 2, 7), date(2025, 3, 9)})

    def test_court_found(self):
        self.assertTrue(d.court_found("Family Court Faridabad", CONTESTED))
        self.assertFalse(d.court_found("Family Court Rohtak Haryana", CONTESTED))
        self.assertIsNone(d.court_found("", CONTESTED))


if __name__ == "__main__":
    unittest.main()
