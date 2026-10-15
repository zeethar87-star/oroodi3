"""Sanity checks for the second source-documented candidate batch (not live offers)."""
import datetime as dt
import json
import unittest
from pathlib import Path
from urllib.parse import urlparse

P = Path(__file__).parent / "2026-10-16" / "batch-02-candidates.json"
DATA = json.loads(P.read_text(encoding="utf-8"))

class BatchTwoTests(unittest.TestCase):
    def test_five_unique_candidates(self):
        ids = [x["id"] for x in DATA["offer_candidates"]]
        self.assertEqual(len(ids), 5)
        self.assertEqual(len(set(ids)), 5)
        self.assertEqual(DATA["status"], "RESEARCH_ONLY_UNAPPROVED_NOT_LIVE")

    def test_official_sources_https(self):
        for offer in DATA["offer_candidates"]:
            parsed = urlparse(offer["source_url"])
            self.assertEqual(parsed.scheme, "https")
            self.assertIn(parsed.hostname, {
                "www.alrajhibank.com.sa", "www.sab.com"
            })

    def test_expiry_conflict_is_quarantined(self):
        for offer in DATA["offer_candidates"]:
            if offer["status"] == "CONFLICTING_EVIDENCE":
                self.assertIsNone(offer["expiry_date"])
                self.assertGreaterEqual(len(offer["conflicting_expiry_dates"]), 2)
            else:
                self.assertGreaterEqual(dt.date.fromisoformat(offer["expiry_date"]),
                                        dt.date(2026, 10, 16))

    def test_no_digital_wallet_inferred_for_rajhi_stily(self):
        offer = next(o for o in DATA["offer_candidates"]
                     if o["id"] == "research-rajhi-stily")
        self.assertEqual(offer["wallet_payment"], "EXCLUDED")

if __name__ == "__main__":
    unittest.main()
