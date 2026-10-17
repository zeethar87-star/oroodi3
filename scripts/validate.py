"""فحص شامل قبل أي دمج: السكيما، القاموس، ومطابقة البيانات الاحتياطية داخل الصفحة،
وفحص الخصوصية (أسرار، مسارات محلية، ملفات .env، إيميلات غير noreply) على الملفات المتتبعة.

الاستخدام:  python scripts/validate.py
يخرج برمز 1 عند أي خطأ، فيوقف طلب الدمج في GitHub تلقائياً.
"""
import sys

import privacy_scan
from oroodi_lib import (MERCHANTS_PATH, OFFERS_PATH, MerchantBook, inline_fallback,
                        load_json, validate_offer, validate_payload)


def main() -> int:
    errors: list[str] = []
    merchants_data = load_json(MERCHANTS_PATH)
    if not merchants_data or not isinstance(merchants_data.get("merchants"), list):
        errors.append("merchants.json مفقود أو تالف")
        merchants_data = {"merchants": []}
    names = [m.get("name") for m in merchants_data["merchants"]]
    if len(names) != len(set(names)):
        errors.append("merchants.json: اسم معتمد مكرر")
    book = MerchantBook(merchants_data)
    seen_forms: dict[str, str] = {}
    from oroodi_lib import normalize_ar
    for m in merchants_data["merchants"]:
        for f in [m["name"], *m.get("aliases", [])]:
            k = normalize_ar(f)
            if k in seen_forms and seen_forms[k] != m["name"]:
                errors.append(f"merchants.json: الصيغة «{f}» مشتركة بين «{seen_forms[k]}» و«{m['name']}»")
            seen_forms[k] = m["name"]

    payload = load_json(OFFERS_PATH)
    if payload is None:
        errors.append("offers.json مفقود")
    else:
        errors += validate_payload(payload, book)
        fb = inline_fallback()
        for o in fb:
            errors += [f"INLINE_FALLBACK → {e}" for e in validate_offer(o, book)]
        if fb != payload.get("offers"):
            errors.append("INLINE_FALLBACK داخل index.html لا يطابق offers.json — شغّل: python scripts/sync_fallback.py")

    # فحص الخصوصية جزء من الفحص الإلزامي، فيشتغل في كل طلب دمج عبر «فحص الجودة»
    errors += [f"الخصوصية → {p}" for p in privacy_scan.scan()]

    if errors:
        print("❌ أخطاء:")
        for e in errors:
            print("  -", e)
        return 1
    print(f"✅ سليم — العروض: {len(payload['offers'])} · المتاجر في القاموس: {len(names)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
