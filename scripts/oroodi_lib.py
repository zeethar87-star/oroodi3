"""مكتبة عروضي المشتركة: قراءة وكتابة البيانات، التحقق من السكيما، توحيد أسماء المتاجر، والدمج.

كل السكربتات في هذا المجلد تعتمد على هذا الملف فقط، وبلا أي مكتبة خارجية
(بايثون القياسية وحدها) حتى تشتغل في GitHub Actions وعلى أي جهاز بلا تثبيت.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OFFERS_PATH = ROOT / "offers.json"
MERCHANTS_PATH = ROOT / "merchants.json"
INDEX_PATH = ROOT / "index.html"
ARCHIVE_PATH = ROOT / "data" / "expired-archive.json"
HEALTH_PATH = ROOT / "data" / "health.json"

RIYADH = timezone(timedelta(hours=3))

PROVIDER_TYPES = {"bank", "wallet", "neobank", "bnpl"}
OFFER_TYPES = {"cashback", "discount", "points", "installment"}
CATEGORIES = {"dining", "shopping", "travel", "fuel", "grocery", "general"}
NETWORKS = {"mada", "visa", "mastercard", "apple_pay"}
REQUIRED = [
    "id", "title", "description", "providerName", "providerType", "offerType",
    "value", "category", "compatibleWith", "expiryDate", "sourceUrl", "terms",
]
FIELD_ORDER = REQUIRED + ["promoCode", "merchantName"]
ALLOWED_FIELDS = set(FIELD_ORDER)

# اختصارات ثابتة لأسماء المزودين في المعرّفات
PROVIDER_SLUGS = {
    "البنك الأهلي السعودي": "snb", "مصرف الراجحي": "alrajhi", "بنك الرياض": "riyad",
    "مصرف الإنماء": "alinma", "الأول": "sab", "البنك السعودي الأول": "sab", "بنك البلاد": "albilad",
    "بنك الجزيرة": "aljazira", "البنك العربي الوطني": "anb", "STC Bank": "stcbank",
    "STC Pay": "stcpay", "urpay": "urpay", "تمارا": "tamara", "Tamara": "tamara",
    "تابي": "tabby", "Tabby": "tabby",
}


# ─── أدوات عامة ─────────────────────────────────────────────────────────────
def today_riyadh() -> date:
    return datetime.now(RIYADH).date()


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_ar(text: str) -> str:
    """تطبيع عربي/لاتيني للمقارنة: نفس منطق normalizeText في الواجهة."""
    s = unicodedata.normalize("NFKD", str(text or "")).lower()
    s = re.sub(r"[ً-ٰۖ-ۭ̀-ͯ]", "", s)
    s = re.sub(r"[أإآا]", "ا", s).replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي")
    s = s.replace("ة", "ه").replace("ـ", "")
    return re.sub(r"\s+", " ", s).strip()


def parse_date(value) -> date | None:
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def is_active(offer: dict, on: date | None = None) -> bool:
    """يوم الانتهاء نفسه يُعتبر سارياً، والمقارنة بتوقيت الرياض."""
    exp = parse_date(offer.get("expiryDate"))
    return exp is not None and exp >= (on or today_riyadh())


# ─── المتاجر ────────────────────────────────────────────────────────────────
class MerchantBook:
    def __init__(self, data: dict | None = None):
        data = data if data is not None else load_json(MERCHANTS_PATH, {"merchants": []})
        self.entries = data.get("merchants", [])
        self._lookup: dict[str, str] = {}
        for m in self.entries:
            name = m["name"]
            for form in [name, *m.get("aliases", [])]:
                self._lookup[normalize_ar(form)] = name

    def canonical(self, raw: str | None) -> tuple[str | None, bool]:
        """يرجع (الاسم المعتمد، هل هو جديد غير موجود في القاموس)."""
        if raw is None or not str(raw).strip():
            return None, False
        key = normalize_ar(raw)
        if key in self._lookup:
            return self._lookup[key], False
        return str(raw).strip(), True

    def forms(self, name: str) -> list[str]:
        for m in self.entries:
            if m["name"] == name:
                return [name, *m.get("aliases", [])]
        return [name]

    def appears_in(self, name: str, text: str) -> bool:
        """فحص حتمي ضد الاختلاق: هل ظهر الاسم أو أحد بدائله حرفياً في نص المصدر؟"""
        hay = normalize_ar(text)
        return any(normalize_ar(f) and normalize_ar(f) in hay for f in self.forms(name))


# ─── التحقق من السكيما ──────────────────────────────────────────────────────
def validate_offer(o: dict, merchants: MerchantBook | None = None) -> list[str]:
    errs = []
    oid = o.get("id", "?")
    for f in REQUIRED:
        v = o.get(f)
        if v is None or v == "":
            errs.append(f"{oid}: الحقل {f} ناقص")
    extra = set(o) - ALLOWED_FIELDS
    if extra:
        errs.append(f"{oid}: حقول غير مسموحة {sorted(extra)}")
    if o.get("providerType") not in PROVIDER_TYPES:
        errs.append(f"{oid}: providerType غير صالح")
    if o.get("offerType") not in OFFER_TYPES:
        errs.append(f"{oid}: offerType غير صالح")
    if o.get("category") not in CATEGORIES:
        errs.append(f"{oid}: category غير صالح")
    cw = o.get("compatibleWith")
    # قائمة فارغة مسموحة = المصدر لم يذكر الشبكات صراحة (لا نخمّن)
    if not isinstance(cw, list) or any(n not in NETWORKS for n in cw):
        errs.append(f"{oid}: compatibleWith غير صالح")
    if parse_date(o.get("expiryDate")) is None:
        errs.append(f"{oid}: expiryDate ليس بصيغة YYYY-MM-DD")
    if not str(o.get("sourceUrl", "")).startswith("https://"):
        errs.append(f"{oid}: sourceUrl يجب أن يبدأ بـ https://")
    if "promoCode" in o and o["promoCode"] is not None and not isinstance(o["promoCode"], str):
        errs.append(f"{oid}: promoCode يجب أن يكون نصاً أو null")
    mn = o.get("merchantName")
    if mn is not None:
        if not isinstance(mn, str) or not mn.strip():
            errs.append(f"{oid}: merchantName يجب أن يكون نصاً أو null")
        elif merchants is not None:
            canon, is_new = merchants.canonical(mn)
            if is_new:
                errs.append(f"{oid}: المتجر «{mn}» غير موجود في merchants.json — أضِفه للقاموس أولاً")
            elif canon != mn:
                errs.append(f"{oid}: merchantName «{mn}» يجب أن يُكتب بالاسم المعتمد «{canon}»")
    return errs


def validate_payload(payload: dict, merchants: MerchantBook | None = None) -> list[str]:
    errs = []
    if not isinstance(payload, dict) or set(payload) != {"lastUpdated", "offers"}:
        return ["الملف يجب أن يحتوي lastUpdated و offers فقط"]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", str(payload["lastUpdated"])):
        errs.append("lastUpdated ليس بصيغة YYYY-MM-DDTHH:mm:ssZ")
    ids = set()
    for o in payload["offers"]:
        errs += validate_offer(o, merchants)
        if o.get("id") in ids:
            errs.append(f"{o.get('id')}: معرّف مكرر")
        ids.add(o.get("id"))
    return errs


def ordered(o: dict) -> dict:
    out = {k: o[k] for k in FIELD_ORDER if k in o}
    out.setdefault("promoCode", None)
    out.setdefault("merchantName", None)
    return out


# ─── الدمج وإزالة التكرار ───────────────────────────────────────────────────
def norm_value(v: str) -> str:
    s = normalize_ar(v)
    s = s.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩٪", "0123456789%"))
    return re.sub(r"\s+", "", s)


def provider_slug(name: str) -> str:
    if name in PROVIDER_SLUGS:
        return PROVIDER_SLUGS[name]
    slug = re.sub(r"[^a-z0-9]+", "-", normalize_ar(name).encode("ascii", "ignore").decode()).strip("-")
    return slug or "provider"


def match_key(o: dict) -> tuple:
    """العنوان لا يدخل في المفتاح أبداً: أكثر حقل يتغير صياغة بلا تغيّر في المعنى."""
    provider = normalize_ar(o.get("providerName", ""))
    if o.get("merchantName"):
        return ("m", provider, normalize_ar(o["merchantName"]), o.get("offerType"), norm_value(o.get("value", "")))
    return ("u", provider, o.get("sourceUrl", "").rstrip("/").lower(), o.get("offerType"), norm_value(o.get("value", "")))


def next_id(o: dict, taken: set[str]) -> str:
    base = f"{provider_slug(o['providerName'])}-{o['category']}"
    n = 1
    while f"{base}-{n:03d}" in taken:
        n += 1
    return f"{base}-{n:03d}"


def merge_offers(existing: list[dict], incoming: list[dict]) -> tuple[list[dict], list[str], list[str]]:
    """يرجع (القائمة المدمجة، معرّفات أضيفت، معرّفات حُدّثت). المعرّف القديم يُحتفظ به دائماً."""
    result = [dict(o) for o in existing]
    index = {match_key(o): i for i, o in enumerate(result)}
    taken = {o["id"] for o in result}
    added, updated = [], []
    for new in incoming:
        key = match_key(new)
        if key in index:
            cur = result[index[key]]
            changed = False
            if (parse_date(new["expiryDate"]) or date.min) > (parse_date(cur["expiryDate"]) or date.min):
                cur["expiryDate"] = new["expiryDate"]
                changed = True
            if len(new.get("terms", "")) > len(cur.get("terms", "")):
                cur["terms"] = new["terms"]
                changed = True
            if not cur.get("merchantName") and new.get("merchantName"):
                cur["merchantName"] = new["merchantName"]
                changed = True
            if changed:
                updated.append(cur["id"])
        else:
            new = dict(new)
            new["id"] = next_id(new, taken)
            taken.add(new["id"])
            result.append(new)
            index[key] = len(result) - 1
            added.append(new["id"])
    return [ordered(o) for o in result], added, updated


CATEGORY_RANK = {"fuel": 0, "grocery": 1, "dining": 2, "travel": 3, "shopping": 4, "general": 5}
TYPE_RANK = {"cashback": 0, "discount": 1, "points": 2, "installment": 3}


def sort_offers(offers: list[dict]) -> list[dict]:
    return sorted(offers, key=lambda o: (
        CATEGORY_RANK.get(o["category"], 9), TYPE_RANK.get(o["offerType"], 9),
        parse_date(o["expiryDate"]) or date.max, o["id"],
    ))


# ─── مزامنة البيانات الاحتياطية داخل الصفحة ──────────────────────────────────
FALLBACK_RE = re.compile(r"(const INLINE_FALLBACK = )(\[.*?\])(;\s*\n)", re.S)


def sync_inline_fallback(offers: list[dict]) -> bool:
    html = INDEX_PATH.read_text(encoding="utf-8")
    m = FALLBACK_RE.search(html)
    if not m:
        raise SystemExit("لم أجد const INLINE_FALLBACK داخل index.html")
    body = json.dumps(offers, ensure_ascii=False, indent=2).replace("</", "<\\/")
    body = "\n".join(("    " + line) if i else line for i, line in enumerate(body.splitlines()))
    new_html = html[:m.start(2)] + body + html[m.end(2):]
    if new_html != html:
        INDEX_PATH.write_text(new_html, encoding="utf-8")
        return True
    return False


def inline_fallback() -> list[dict]:
    m = FALLBACK_RE.search(INDEX_PATH.read_text(encoding="utf-8"))
    return json.loads(m.group(2).replace("<\\/", "</")) if m else []
