import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from analyser.verify import deathcommon as dc, mcd, ndmc

WANT = {"name": "Ram Kumar", "gender": "Male", "dod": "2026-03-12", "father": "Hari Lal", "mother": "Gita Devi",
        "reg_no": "D-2026:06-1234", "reg_date": "2026-03-20", "unit": "MCF NIT", "place": "Faridabad"}

INLINE = """Registration Number : D-2026:06-1234
Name Of Deceased : Ram Kumar
Gender : Male
Date of Death : 12/03/2026
Place of Death : Faridabad
Name Of Father : Hari Lal
Name Of Mother : Gita Devi
Registration Date : 20-03-2026
Registration Unit Name : MCF NIT"""

TABS = INLINE.replace(" : ", "\t")

NEXT_LINE = """Registration Number
D-2026:06-1234
Name
Ram Kumar
Gender
Male
Date of Death
12 March 2026
Place of Death
Faridabad
Name of Father
Hari Lal
Name of Mother
Gita Devi
Registration Date
20/03/2026
Registration Unit Name
MCF NIT"""

BLOCKS = """Registration Number
Name
Gender
Date of Death
Place of Death
Name of Father
Name of Mother
Registration Date
Registration Unit Name
D-2026:06-1234
Ram Kumar
Male
12-03-2026
Faridabad
Hari Lal
Gita Devi
20-03-2026
MCF NIT"""


class Parse(unittest.TestCase):
    def test_four_layouts(self):
        for text in (INLINE, TABS, NEXT_LINE, BLOCKS):
            self.assertEqual(dc.parse(text), WANT, text[:40])

    def test_husband_and_noise(self):
        t = "Death Certificate\nGovernment of NCT\nName of Deceased : Sita Devi\nName of Husband : Mohan Lal\nDate of Death : 05.06.2019\nDownload\n"
        self.assertEqual(dc.parse(t), {"name": "Sita Devi", "spouse": "Mohan Lal", "dod": "2019-06-05"})

    def test_first_value_wins_and_bad_date_dropped(self):
        t = "Name : A One\nName : B Two\nDate of Death : not a date\n"
        self.assertEqual(dc.parse(t), {"name": "A One"})

    def test_nothing(self):
        self.assertEqual(dc.parse("Welcome to the portal\nLogin"), {})


NDMC_PAGE = """Government of NCT
Organization Name: -
North Delhi Municipal Corporation
Application Number: -
D/2025/1
Name: -
Sita Devi
Date Of Event: -
25-10-2025 05:30
Gender: -
Female
Place Of Event: -
Civil Lines
Activity Type: -
Death
Registration Number: -
148000
Registration Date: -
27-10-2025
Mother Name: -
Gita Devi
Mother UID No.: -
123
Father Name: -
Hari Lal
Husband/Wife Name: -
Mohan Lal
Husband/Wife UID No.: -
456
Issue Date: -
21-10-2026 02:10"""


class NdmcLayout(unittest.TestCase):
    def test_label_dash_then_value_on_next_line(self):
        f = dc.parse(NDMC_PAGE)
        self.assertEqual((f["name"], f["dod"], f["gender"], f["place"], f["activity"]),
                         ("Sita Devi", "2025-10-25", "Female", "Civil Lines", "Death"))
        self.assertEqual((f["reg_no"], f["reg_date"], f["mother"], f["father"], f["spouse"]),
                         ("148000", "2025-10-27", "Gita Devi", "Hari Lal", "Mohan Lal"))


class Mcd(unittest.TestCase):
    QR = "Name Of The Deceased RAM KUMAR Registration No 5 Verified URL: https://mcdonline.nic.in/rbd/web/citizen/hospital/verifyCertificate?x=1&y=2"
    PAGE = ("<html><style>.a{}</style><body><h1>Verify</h1><h2>Certificate Details</h2><table>"
            "<tr><td>Name</td><td>Ram Kumar</td></tr><tr><td>Date Of Death</td><td>12/03/2026</td></tr>"
            "<tr><td>Registration No</td><td>D-2026:1</td></tr><tr><td>Name of Father</td><td>Hari Lal</td></tr></table></body></html>")

    def test_url_extracted(self):
        self.assertTrue(mcd.verify_url(self.QR).endswith("?x=1&y=2"))

    def test_verified(self):
        with mock.patch.object(mcd, "fetch", return_value=(self.PAGE.encode(), "")):
            rec = mcd.verify(self.QR)
        self.assertEqual((rec.status, rec.fields["name"], rec.fields["dod"], rec.fields["father"]), ("verified", "Ram Kumar", "2026-03-12", "Hari Lal"))

    def test_no_record_during_maintenance(self):
        page = b"<html><body>No Record Found</body></html>"
        with mock.patch.object(mcd, "fetch", return_value=(page, "")):
            night = mcd.verify(self.QR, now=datetime(2026, 10, 21, 23, 30, tzinfo=mcd.IST))
            day = mcd.verify(self.QR, now=datetime(2026, 10, 21, 12, 0, tzinfo=mcd.IST))
        self.assertIn("maintenance", night.error)
        self.assertEqual(day.error, "No Record Found")
        self.assertEqual(night.status, "failed")


class Ndmc(unittest.TestCase):
    OK = "Death Certificate\nName of Deceased\tSita Devi\nName of Husband\tMohan Lal\nDate of Death\t05/06/2019\nRegistration No\t148000"

    def verify(self, renders, **kw):
        with mock.patch.object(ndmc, "render", side_effect=renders), mock.patch.object(ndmc.time, "sleep") as sleep, \
                mock.patch.object(ndmc, "CACHE", Path(tempfile.mkdtemp())):
            return ndmc.verify("https://bnd.ndmc.gov.in/verify-certificate/abc", **kw), sleep

    def test_rate_limit_then_success(self):
        rec, sleep = self.verify([("Too many requests", ""), (self.OK, "")])
        self.assertEqual((rec.status, rec.fields["spouse"], rec.fields["dod"]), ("verified", "Mohan Lal", "2019-06-05"))
        self.assertIn(mock.call(ndmc.BACKOFF), sleep.call_args_list)

    def test_gives_up_after_retries(self):
        rec, _ = self.verify([("Too many requests", "")] * 2, retries=2)
        self.assertEqual((rec.status, rec.error), ("failed", "NDMC rate limit"))

    def test_browser_error_and_empty_shell(self):
        self.assertEqual(self.verify([("", "Error net::ERR_CERT_AUTHORITY_INVALID")])[0].error, "Error net::ERR_CERT_AUTHORITY_INVALID")
        self.assertEqual(self.verify([("Verify Certificate", "")])[0].error, "page showed no certificate record")


class ErrorCode(unittest.TestCase):
    def test_no_url_in_message(self):
        from analyser.verify import browser
        e = Exception('Page.goto: net::ERR_NAME_NOT_RESOLVED at https://x.example/verify?id=SECRETSECRETSECRET1234')
        self.assertEqual(browser.error_code(e), "Exception net::ERR_NAME_NOT_RESOLVED")
        self.assertNotIn("SECRET", browser.error_code(Exception('failed to load "https://x.example/a?id=SECRETSECRETSECRET1234"')))


if __name__ == "__main__":
    unittest.main()
