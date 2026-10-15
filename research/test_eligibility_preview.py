"""Offline tests for the research-only candidate matcher."""
import json
import unittest
from pathlib import Path
from research.eligibility_preview import audit_data, evaluate

DATA_PATH = Path(__file__).parent / "2026-10-16" / "offer-candidates.json"
DATA = json.loads(DATA_PATH.read_text(encoding="utf-8"))
OFFERS = {o["id"]: o for o in DATA["offer_candidates"]}

class EligibilityPreviewTests(unittest.TestCase):
    def test_dataset_integrity(self):
        self.assertEqual(audit_data(DATA), 8)

    def test_stc_bafello_full_published_match(self):
        card = dict(issuer="بنك إس تي سي", card_type="credit",
                    payment_method="apple_pay", channel="online",
                    promo_code="STCB50")
        self.assertEqual(evaluate(OFFERS["research-stc-bafello"], card,
                                  "2026-10-16")["status"], "MATCH")

    def test_wrong_bank_cannot_match(self):
        card = dict(issuer="بنك الرياض")
        self.assertEqual(evaluate(OFFERS["research-stc-bafello"], card,
                                  "2026-10-16")["status"], "NOT_ELIGIBLE")

    def test_expiry_is_inclusive(self):
        card = dict(issuer="بنك إس تي سي", card_type="credit",
                    payment_method="apple_pay", channel="online",
                    promo_code="STCB50")
        self.assertEqual(evaluate(OFFERS["research-stc-bafello"], card,
                                  "2026-10-31")["status"], "MATCH")
        self.assertEqual(evaluate(OFFERS["research-stc-bafello"], card,
                                  "2026-11-01")["status"], "NOT_ELIGIBLE")

    def test_missing_code_stays_conditional(self):
        card = dict(issuer="بنك إس تي سي", card_type="credit",
                    payment_method="apple_pay", channel="online")
        self.assertEqual(evaluate(OFFERS["research-stc-bafello"], card,
                                  "2026-10-16")["status"], "CONDITIONAL")

    def test_anb_targeted_uninvited_not_eligible(self):
        card = dict(issuer="البنك العربي الوطني", invited=False)
        self.assertEqual(evaluate(OFFERS["research-anb-oct-cashback"], card,
                                  "2026-10-16")["status"], "NOT_ELIGIBLE")

    def test_anb_targeted_unknown_invitation(self):
        card = dict(issuer="البنك العربي الوطني")
        self.assertEqual(evaluate(OFFERS["research-anb-oct-cashback"], card,
                                  "2026-10-16")["status"], "UNKNOWN")

    def test_ihg_conflict_never_auto_match(self):
        card = dict(issuer="البنك الأهلي السعودي")
        self.assertEqual(evaluate(OFFERS["research-snb-ihg-conflict"], card,
                                  "2026-10-16")["status"], "UNKNOWN")

    def test_branch_city_spend_and_delivery(self):
        candidate=OFFERS["research-stc-lolivo"]
        base=dict(issuer="بنك إس تي سي",card_type="mada",
                  payment_method="card_direct",channel="in_store",city="Riyadh",
                  spend_sar=50)
        self.assertEqual(evaluate(candidate,base,"2026-10-16")["status"],"MATCH")
        self.assertEqual(evaluate(candidate,{**base,"city":"Dammam"},
                                  "2026-10-16")["status"],"NOT_ELIGIBLE")
        self.assertEqual(evaluate(candidate,{**base,"spend_sar":20},
                                  "2026-10-16")["status"],"NOT_ELIGIBLE")
        self.assertEqual(evaluate(candidate,{**base,"channel":"delivery_app"},
                                  "2026-10-16")["status"],"NOT_ELIGIBLE")

    def test_missing_conditions_dont_become_match(self):
        card=dict(issuer="البنك الأهلي السعودي",card_type="credit")
        self.assertEqual(evaluate(OFFERS["research-snb-aani-dani"],card,
                                  "2026-10-16")["status"],"CONDITIONAL")

if __name__ == "__main__":
    unittest.main()
