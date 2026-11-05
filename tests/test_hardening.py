import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from analyser import run, store
from analyser.load import Request
from analyser.verify import base, browser


class Fetch(unittest.TestCase):
    def fake_curl(self, final_url, body=b"%PDF-1.4 x", code=0):
        def runner(cmd, **kw):
            if code == 0:
                Path(cmd[cmd.index("-o") + 1]).write_bytes(body)
            return subprocess.CompletedProcess(cmd, code, stdout=final_url.encode(), stderr=b"")
        return runner

    def fetch(self, runner, url="https://online.ulbharyana.gov.in/x?a=1"):
        with mock.patch.object(base, "CACHE", Path(tempfile.mkdtemp())), mock.patch.object(base.subprocess, "run", side_effect=runner), \
                mock.patch.object(base.time, "sleep"):
            return base.fetch(url, retries=1)

    def test_government_site_is_kept(self):
        self.assertEqual(self.fetch(self.fake_curl("https://online.ulbharyana.gov.in/x?a=1")), (b"%PDF-1.4 x", ""))

    def test_redirect_to_another_site_is_discarded(self):
        data, err = self.fetch(self.fake_curl("https://evil.example.com/steal"))
        self.assertEqual((data, err), (None, "redirected to a non government site"))

    def test_lookalike_host_is_discarded(self):
        self.assertIsNone(self.fetch(self.fake_curl("https://crsorgi.gov.in.evil.com/x"))[0])

    def test_curl_failure_leaves_no_file(self):
        cache = Path(tempfile.mkdtemp())
        with mock.patch.object(base, "CACHE", cache), mock.patch.object(base.subprocess, "run", side_effect=self.fake_curl("", code=22)), \
                mock.patch.object(base.time, "sleep"):
            self.assertEqual(base.fetch("https://x.gov.in/a", retries=1), (None, "curl exit 22"))
        self.assertEqual(list(cache.iterdir()), [])


class BrowserGate(unittest.TestCase):
    def test_only_government_hosts(self):
        for url in ("https://dc.crsorgi.gov.in/crs/x", "https://bnd.ndmc.gov.in/a", "https://mcdonline.nic.in/b", "data:text/css,a{}"):
            self.assertTrue(browser.allowed_request(url), url)
        for url in ("https://fonts.googleapis.com/css", "https://www.google-analytics.com/c", "https://gov.in.evil.com/x",
                    "https://evil.com/?u=https://crsorgi.gov.in/", "http://127.0.0.1:8766/"):
            self.assertFalse(browser.allowed_request(url), url)


class Store(unittest.TestCase):
    def test_lock_down_makes_everything_owner_only(self):
        root = Path(tempfile.mkdtemp()) / "store"
        (root / "cache" / "verify").mkdir(parents=True)
        (root / "cache" / "verify" / "a.bin").write_bytes(b"x")
        (root / "results.json").write_text("{}")
        os.chmod(root / "cache" / "verify" / "a.bin", 0o644)
        store.lock_down(root)
        for p in [root, *root.rglob("*")]:
            mode = stat.S_IMODE(p.stat().st_mode)
            self.assertEqual(mode & 0o077, 0, p.name)

    def test_result_record_never_holds_mobile_numbers(self):
        raw = {"request_id": "1", "list_row": {"Request Type": "Widow", "FamilyID": "F1", "Mobile No": "9876543210"},
               "case": {"User Info": {"Name": "Sita Devi", "Mobile Number": "9876543210", "Requested Status In PPP": "Widow",
                                      "Aadhaar": "123412341234"}},
               "family": [{"Full Name": "Sita Devi", "Mobile No": "9876543210"}]}
        req = Request("marital", "/nonexistent", raw)
        d = run.decide_for_store(req)
        text = json.dumps(run.record_for(req, d, "t"))
        self.assertNotIn("9876543210", text)
        self.assertNotIn("123412341234", text)


if __name__ == "__main__":
    unittest.main()
