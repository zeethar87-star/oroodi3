"""ينسخ العروض من offers.json إلى INLINE_FALLBACK داخل index.html.

البيانات الاحتياطية هي ما يظهر لو فشل تحميل offers.json (بلا إنترنت مثلاً)،
فلازم تبقى مطابقة للمصدر الوحيد للحقيقة: offers.json.
"""
from oroodi_lib import OFFERS_PATH, load_json, sync_inline_fallback

if __name__ == "__main__":
    changed = sync_inline_fallback(load_json(OFFERS_PATH)["offers"])
    print("تم تحديث INLINE_FALLBACK" if changed else "INLINE_FALLBACK مطابق بالفعل")
