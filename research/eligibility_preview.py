#!/usr/bin/env python3
"""Conservative offline preview. Research-only; never edits offers.json."""
import argparse
import datetime as dt
import json
from pathlib import Path

DEFAULT_DATA = Path(__file__).resolve().parent / "2026-10-16" / "offer-candidates.json"
VALID_STATUSES = {
    "VERIFIED_PUBLISHED_ACTIVE", "VERIFIED_TARGETED", "CONFLICTING_EVIDENCE"
}

def audit_data(data):
    if data.get("status") != "RESEARCH_ONLY_UNAPPROVED_NOT_LIVE":
        raise ValueError("Research-only dataset marker is required")
    ids = set()
    for offer in data["offer_candidates"]:
        if offer["id"] in ids:
            raise ValueError("Duplicate candidate ID: " + offer["id"])
        ids.add(offer["id"])
        if offer["status"] not in VALID_STATUSES:
            raise ValueError("Unexpected status: " + offer["status"])
        if not str(offer["source_url"]).startswith("https://"):
            raise ValueError("Non-HTTPS official source")
        if offer["status"] != "CONFLICTING_EVIDENCE":
            if not offer.get("expiry_date"):
                raise ValueError("Missing expiry date")
            dt.date.fromisoformat(offer["expiry_date"])
        if offer.get("start_date"):
            dt.date.fromisoformat(offer["start_date"])
        if offer["status"] == "CONFLICTING_EVIDENCE":
            if len(offer.get("conflicting_expiry_dates", [])) < 2:
                raise ValueError("Date conflict must retain both alternatives")
    return len(ids)

def evaluate(offer, card, when):
    """Classification from explicitly listed terms. MATCH never guarantees redemption."""
    today = dt.date.fromisoformat(when)
    if offer["status"] == "CONFLICTING_EVIDENCE":
        return {"status": "UNKNOWN", "reasons": ["تعارض رسمي في انتهاء العرض"]}
    until = offer.get("expiry_date")
    if not until:
        return {"status": "UNKNOWN", "reasons": ["تاريخ انتهاء غير مثبت"]}
    if today > dt.date.fromisoformat(until):
        return {"status": "NOT_ELIGIBLE", "reasons": ["انتهى العرض"]}
    if offer.get("start_date") and today < dt.date.fromisoformat(offer["start_date"]):
        return {"status": "NOT_ELIGIBLE", "reasons": ["العرض لم يبدأ"]}
    if not card.get("issuer"):
        return {"status": "UNKNOWN", "reasons": ["الجهة المصدرة غير معروفة"]}
    if card["issuer"] != offer["issuer"]:
        return {"status": "NOT_ELIGIBLE", "reasons": ["جهة الإصدار غير مطابقة"]}
    rules = offer["eligibility"]
    pending = []
    if rules.get("targeted"):
        if card.get("invited") is False:
            return {"status": "NOT_ELIGIBLE", "reasons": ["لم تصلك دعوة للعرض الخاص"]}
        if card.get("invited") is not True:
            return {"status": "UNKNOWN", "reasons": ["تتطلب الحملة دعوة شخصية موثقة"]}
    for rule_key, card_key, reason in [
        ("card_types", "card_type", "نوع البطاقة"),
        ("accepted_payment_methods", "payment_method", "طريقة الدفع"),
        ("channels", "channel", "قناة الشراء")
    ]:
        accepted = rules.get(rule_key, [])
        selected = card.get(card_key)
        if not accepted:
            pending.append("لا توجد تفاصيل كافية عن " + reason)
        elif selected is None:
            pending.append("لم تُحدد " + reason)
        elif selected not in accepted:
            return {"status": "NOT_ELIGIBLE", "reasons": [reason + " غير مؤهلة"]}
    excluded = rules.get("excluded_channels", [])
    if card.get("channel") in excluded:
        return {"status": "NOT_ELIGIBLE", "reasons": ["القناة مستبعدة رسميًا"]}
    city = rules.get("city")
    if city:
        if card.get("city") is None:
            pending.append("المدينة غير معروفة")
        elif card["city"].casefold() != city.casefold():
            return {"status": "NOT_ELIGIBLE", "reasons": ["العرض مرتبط بمدينة أخرى"]}
    code = rules.get("promo_code")
    if code:
        if not card.get("promo_code"):
            pending.append("يلزم رمز ترويجي")
        elif card["promo_code"].casefold() != code.casefold():
            return {"status": "NOT_ELIGIBLE", "reasons": ["الرمز الترويجي غير مطابق"]}
    minimum = rules.get("minimum_spend_sar")
    if minimum is not None and minimum > 0:
        if card.get("spend_sar") is None:
            pending.append("قيمة الإنفاق غير معروفة")
        elif card["spend_sar"] < minimum:
            return {"status": "NOT_ELIGIBLE", "reasons": ["الإنفاق دون الحد الأدنى"]}
    if rules.get("requires_card_presentation"):
        if card.get("card_presented") is False:
            return {"status": "NOT_ELIGIBLE", "reasons": ["إبراز البطاقة مطلوب"]}
        if card.get("card_presented") is not True:
            pending.append("يجب إبلاغ الموظف وإبراز البطاقة")
    if rules.get("targeted") and offer.get("value") is None:
        pending.append("القيمة الخاصة للعميل غير منشورة")
    status = "CONDITIONAL" if pending else "MATCH"
    return {
        "status": status,
        "reasons": pending or ["مطابقة للشروط المدخلة فقط؛ قبول المعاملة غير مضمون"],
    }

def main():
    parser = argparse.ArgumentParser(description="Research-only eligibility preview")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--date", default="2026-10-16")
    parser.add_argument("--offer-id")
    parser.add_argument("--issuer")
    parser.add_argument("--card-type")
    parser.add_argument("--payment-method")
    parser.add_argument("--channel")
    parser.add_argument("--city")
    parser.add_argument("--promo-code")
    parser.add_argument("--spend-sar", type=float)
    parser.add_argument("--invited", choices=["yes", "no", "unknown"], default="unknown")
    parser.add_argument("--card-presented", action="store_true")
    args = parser.parse_args()
    data = json.loads(args.data.read_text(encoding="utf-8"))
    total = audit_data(data)
    if not args.offer_id:
        print(json.dumps({"audit": "PASS", "candidate_count": total,
                          "production_impact": "NONE"}, ensure_ascii=False))
        return
    offer = next((o for o in data["offer_candidates"]
                  if o["id"] == args.offer_id), None)
    if offer is None:
        parser.error("Offer ID not found")
    card = {
        "issuer": args.issuer, "card_type": args.card_type,
        "payment_method": args.payment_method, "channel": args.channel,
        "city": args.city, "promo_code": args.promo_code,
        "spend_sar": args.spend_sar,
        "invited": {"yes": True, "no": False, "unknown": None}[args.invited],
        "card_presented": args.card_presented
    }
    print(json.dumps({
        "offer_id": offer["id"], "classification": evaluate(offer, card, args.date),
        "disclaimer": "بحث تجريبي لا يضمن الخصم أو صلاحية العرض عند الدفع",
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
