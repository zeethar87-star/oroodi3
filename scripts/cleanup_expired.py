"""التنظيف الدوري: ينقل العروض المنتهية إلى الأرشيف ويحدّث ملف الصحة.

- يوم الانتهاء نفسه يُعتبر سارياً، والمقارنة بتوقيت الرياض.
- لا يحذف شيئاً نهائياً: كل منتهٍ يُنقل إلى data/expired-archive.json
  (مفيد لإعادة التحقق من عروض تتجدد سنوياً).
- يكتب data/health.json في كل تشغيل؛ هذا "النبض" يمنع GitHub من إيقاف
  الجدولة بصمت في المستودعات العامة بعد ستين يوماً بلا نشاط.
"""
import sys

from oroodi_lib import (ARCHIVE_PATH, HEALTH_PATH, OFFERS_PATH, is_active, load_json,
                        now_utc_iso, save_json, sort_offers, sync_inline_fallback, today_riyadh)


def main() -> int:
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

    soon = sorted((o for o in active), key=lambda o: o["expiryDate"])[:5]
    save_json(HEALTH_PATH, {
        "lastCheck": now_utc_iso(),
        "checkedDateRiyadh": today.isoformat(),
        "activeOffers": len(active),
        "removedThisRun": [o["id"] for o in expired],
        "withMerchant": sum(1 for o in active if o.get("merchantName")),
        "nextToExpire": [{"id": o["id"], "expiryDate": o["expiryDate"]} for o in soon],
        "warning": "أقل من 10 عروض سارية — الموقع يحتاج إضافة عروض جديدة" if len(active) < 10 else None,
    })
    print(f"سارية: {len(active)} — نُقلت للأرشيف: {len(expired)}")
    for o in expired:
        print("  أرشيف:", o["id"], o["expiryDate"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
