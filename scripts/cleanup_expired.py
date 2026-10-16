"""التنظيف الدوري: ينقل العروض المنتهية إلى الأرشيف ويحدّث ملف الصحة.

- يوم الانتهاء نفسه يُعتبر سارياً، والمقارنة بتوقيت الرياض.
- لا يحذف شيئاً نهائياً: كل منتهٍ يُنقل إلى data/expired-archive.json
  (مفيد لإعادة التحقق من عروض تتجدد سنوياً).
- يكتب data/health.json في كل تشغيل؛ هذا "النبض" يمنع GitHub من إيقاف
  الجدولة بصمت في المستودعات العامة بعد ستين يوماً بلا نشاط.

الوضع --health-only: يكتب ملف الصحة فقط من offers.json كما هو، بلا أرشفة ولا
لمس للعروض. تشغّله أتمتة «تحديث ملف الصحة» بعد كل دمج يغيّر offers.json.
ولا يكتب الملف لو لم يتغير فيه شيء غير وقت الفحص، فلا تُصنع commits فارغة.
"""
import sys

from oroodi_lib import (ARCHIVE_PATH, HEALTH_PATH, OFFERS_PATH, is_active, load_json,
                        now_utc_iso, save_json, sort_offers, sync_inline_fallback, today_riyadh)


def build_health(active: list[dict], removed: list[dict], today) -> dict:
    soon = sorted(active, key=lambda o: o["expiryDate"])[:5]
    return {
        "lastCheck": now_utc_iso(),
        "checkedDateRiyadh": today.isoformat(),
        "activeOffers": len(active),
        "removedThisRun": [o["id"] for o in removed],
        "withMerchant": sum(1 for o in active if o.get("merchantName")),
        "nextToExpire": [{"id": o["id"], "expiryDate": o["expiryDate"]} for o in soon],
        "warning": "أقل من 10 عروض سارية — الموقع يحتاج إضافة عروض جديدة" if len(active) < 10 else None,
    }


def health_only() -> int:
    """يكتب ملف الصحة فقط؛ لا يعدّل offers.json ولا الأرشيف."""
    payload = load_json(OFFERS_PATH)
    today = today_riyadh()
    active = [o for o in payload["offers"] if is_active(o, today)]
    new = build_health(active, [], today)
    old = load_json(HEALTH_PATH, {}) or {}
    strip = lambda d: {k: v for k, v in d.items() if k != "lastCheck"}
    if strip(old) == strip(new):
        print(f"ملف الصحة مطابق — سارية: {len(active)}")
        return 0
    save_json(HEALTH_PATH, new)
    print(f"ملف الصحة اتحدّث — سارية: {len(active)}")
    return 0


def main() -> int:
    if "--health-only" in sys.argv[1:]:
        return health_only()
    payload = load_json(OFFERS_PATH)
    today = today_riyadh()
    active = [o for o in payload["offers"] if is_active(o, today)]
    expired = [o for o in payload["offers"] if not is_active(o, today)]

    if expired:
        archive = load_json(ARCHIVE_PATH, {"offers": []})
        known = {o["id"] for o in archive["offers"]}
        stamp = today.isoformat()
        for o in expired:
            if o["id"] not in known:
                archive["offers"].append({**o, "_archivedOn": stamp})
        save_json(ARCHIVE_PATH, archive)
        payload["offers"] = sort_offers(active)
        payload["lastUpdated"] = now_utc_iso()
        save_json(OFFERS_PATH, payload)
        sync_inline_fallback(payload["offers"])

    save_json(HEALTH_PATH, build_health(active, expired, today))
    print(f"سارية: {len(active)} — نُقلت للأرشيف: {len(expired)}")
    for o in expired:
        print("  أرشيف:", o["id"], o["expiryDate"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
