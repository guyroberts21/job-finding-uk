"""Offline tests: run with  python -m unittest discover -s tests"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "fetcher"))
import fetch_jobs as fj  # noqa: E402


class Helpers(unittest.TestCase):
    def test_dates(self):
        self.assertEqual(fj.parse_uk_date("20/12/2026"), "2026-12-20")
        self.assertEqual(fj.parse_uk_date("2026-11-13T09:00:00Z"), "2026-11-13")
        self.assertIsNone(fj.parse_uk_date("not a date"))

    def test_sponsorship(self):
        self.assertEqual(fj.sponsorship_status("We are unable to offer visa sponsorship."), "not_offered")
        self.assertEqual(fj.sponsorship_status("Visa sponsorship is available."), "offered")
        self.assertEqual(fj.sponsorship_status("You must already have the right to work in the UK."), "rtw_required")
        self.assertEqual(fj.sponsorship_status("A great role."), "not_stated")

    def test_process_heavy_form(self):
        p = fj.estimate_process("Complete the application form. CVs will not be accepted.",
                                "https://x.webitrent.com/apply", "Reed", True, ["No CVs accepted"])
        self.assertIn("supporting statement", p["type"])
        self.assertGreaterEqual(p["minutes_low"], 120)

    def test_quick_apply(self):
        p = fj.estimate_process("Send your CV today", "https://www.reed.co.uk/jobs/1", "Reed", False, [])
        self.assertLessEqual(p["minutes_high"], 70)

    def test_score_penalises_senior(self):
        junior = fj.match_score("Communications Assistant", "social media content events community graduate", [])
        senior = fj.match_score("Senior Communications Manager", "social media content events community", [])
        self.assertGreater(junior["score"], senior["score"] + 30)

    def test_responsibilities_from_list(self):
        text, groups = fj.parse_description("<p><strong>Key responsibilities:</strong></p><ul><li>Support residents at digital sessions</li><li>Plan community events</li></ul><p><strong>About you</strong></p><ul><li>Good communicator</li></ul>")
        self.assertEqual(fj.extract_responsibilities(groups, text), ["Support residents at digital sessions", "Plan community events"])


class EndToEnd(unittest.TestCase):
    def test_fixture_run(self):
        tmp = tempfile.mkdtemp()
        try:
            shutil.copytree(ROOT, os.path.join(tmp, "repo"), ignore=shutil.ignore_patterns(".git", "data", "jobs.json"))
            repo = os.path.join(tmp, "repo")
            env = {**os.environ, "JOBFINDER_FIXTURES": os.path.join(repo, "tests", "fixtures"),
                   "JOBFINDER_SKIP_LINK_CHECK": "1", "JOBFINDER_TODAY": "2026-11-18"}
            env.pop("REED_API_KEY", None)
            subprocess.run([sys.executable, os.path.join(repo, "fetcher", "fetch_jobs.py")], env=env, check=True)
            data = json.load(open(os.path.join(repo, "docs", "data", "jobs.json")))
            titles = [j["title"] for j in data["jobs"]]
            self.assertIn("Digital Inclusion Assistant", titles)
            self.assertNotIn("Warehouse Operative", titles)        # excluded title
            self.assertNotIn("Administration Assistant", titles)   # expired
            self.assertEqual(titles.count("Digital Inclusion Assistant"), 1)  # de-duplicated across sources
            for j in data["jobs"]:
                self.assertTrue(j["listing_url"].startswith("https://"))
                self.assertTrue(j["apply_url"].startswith("https://"))
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
