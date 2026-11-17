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
        self.assertEqual(fj.sponsorship_status("This post will not be open to Sponsorship under the UKVI scheme."), "not_offered")
        self.assertEqual(fj.sponsorship_status("Only apply if eligible to work in the UK (indefinitely & without sponsorship)."), "not_offered")
        self.assertEqual(fj.sponsorship_status("Sponsorship of professional qualifications through our panel."), "not_stated")

    def test_process_heavy_form(self):
        p = fj.estimate_process("Complete the application form. CVs will not be accepted.",
                                "https://x.webitrent.com/apply", "Reed", True, ["No CVs accepted"])
        self.assertIn("supporting statement", p["type"])
        self.assertGreaterEqual(p["minutes_low"], 120)

    def test_quick_apply(self):
        p = fj.estimate_process("Please send your CV as a Word document today", "https://www.reed.co.uk/jobs/1", "Reed", False, [])
        self.assertEqual(p["type"], "Quick apply on Reed (CV)")  # Reed strips emails; the CV goes via Reed
        self.assertIn("The advert asks for the CV as a Word document", p["notes"])
        p = fj.estimate_process("Email your CV to us", "https://employer.example/jobs/1", "Reed", True, [])
        self.assertEqual(p["type"], "Email CV + covering letter")
        self.assertLessEqual(p["minutes_high"], 70)

    def test_score_penalises_senior(self):
        junior = fj.match_score("Communications Assistant", "social media content events community graduate", [])
        senior = fj.match_score("Senior Communications Manager", "social media content events community", [])
        self.assertGreater(junior["score"], senior["score"] + 30)

    def test_reed_self_link_is_not_external(self):
        # Reed's API returns the Reed listing as externalUrl when there's no employer link.
        url = "https://www.reed.co.uk/jobs/admin-assistant/123"
        job = fj.build_job("reed-123", "Reed", {"jobId": 123, "jobTitle": "Admin Assistant"},
                           {"jobTitle": "Admin Assistant", "jobUrl": url, "externalUrl": url,
                            "jobDescription": "<p>Support the office team with admin and customer enquiries.</p>"},
                           {"admin"}, {"london"}, None)
        self.assertEqual(job["apply_url"], url)
        self.assertEqual(job["apply_via"], "Reed (quick apply)")
        self.assertEqual(job["process"]["type"], "Quick apply on Reed (CV)")
        ext = fj.build_job("reed-124", "Reed", {"jobId": 124, "jobTitle": "Admin Assistant"},
                           {"jobTitle": "Admin Assistant", "jobUrl": url, "externalUrl": "https://jobs.example.org/apply/9",
                            "jobDescription": "<p>Support the office team.</p>"}, {"admin"}, {"london"}, None)
        self.assertEqual(ext["apply_url"], "https://jobs.example.org/apply/9")
        self.assertTrue(ext["process"]["type"].startswith("Apply on employer"))

    def test_responsibilities_from_list(self):
        text, groups = fj.parse_description("<p><strong>Key responsibilities:</strong></p><ul><li>Support residents at digital sessions</li><li>Plan community events</li></ul><p><strong>About you</strong></p><ul><li>Good communicator</li></ul>")
        self.assertEqual(fj.extract_responsibilities(groups, text), ["Support residents at digital sessions", "Plan community events"])


class EndToEnd(unittest.TestCase):
    def test_fixture_run(self):
        tmp = tempfile.mkdtemp()
        try:
            shutil.copytree(ROOT, os.path.join(tmp, "repo"), ignore=shutil.ignore_patterns(".git", "data", "jobs.json", ".env"))
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
