# -*- coding: utf-8 -*-
"""سبر sitemap الراجحي من GitHub Actions — أصغر تجربة قبل قناة «كشف الجديد».

يجيب على سؤال oroodi3/QUEUE.md رقم 6: هل sitemap.xml نفسه يتسحب من نطاق
GitHub Actions؟ (فشل «الكلاود» السابق كان من بروكسي تجاري، مش من Actions —
ودرس «قياسات من البيت» بيقول: القرار من نطاق التشغيل الفعلي أو مفيش قرار).

ما يفعله السكربت (وما لا يفعله):
- سحب واحد RAW بنفس هوية المشروع المعلنة: نفس User-Agent ونفس الرؤوس بتاعة
  extract_offers.fetch() حرفيًا (Accept-Language: ar,en;q=0.8، مهلة 30 ثانية).
- بلا جافاسكربت، بلا أي مفتاح AI، بلا أي آلية التفاف على حجب محتمل.
- يسجّل: كود HTTP أو نوع الاستثناء بالنص، حجم التنزيل بالبايت وsha256 له،
  عدد كل الروابط <loc>، عدد روابط CardsOffers بالتعريف القانوني
  («/CardsOffers/» في المسار) وتقسيمها عربي/مرايا إنجليزية، وتوزيع lastmod.
- يقارن باللقطة المرجعية المحلية وMaster النجاح المسجّل مسبقًا في كارت التشغيل:
  HTTP 200 + عدد CardsOffers في حدود ±5% من 2496.
- فشل السحب قياس يُسجَّل، مش كسر شغلانة: النتيجة تُرفع artifact دايماً.
- لا يكتب على offers.json ولا على أي بيانات، ولا يعدّل oroodi_lib.py.

المرجعية (لقطة محلية محفوظة، اتحققت بالكود ليلة 2026-10-03):
  ZEIT-Research/oroodi3/curl_bodies/rajhi_sitemap_20261003_011257.xml
  = 4613 رابط / 2496 CardsOffers (1246 عربي + 1250 مرآة إنجليزية) / 2472909 بايت.

التشغيل المحلي:  python scripts/probe_sitemap.py --out ../sitemap-probe-results
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

SITEMAP_URL = "https://www.alrajhibank.com.sa/sitemap.xml"

# نفس هوية السحب المعلنة في المشروع. الاستيراد من extract_offers يضمن أنها لا تنحرف؛
# القيمة الاحتياطية نسخة حرفية منها (تُفحص المطابقة عند التشغيل).
_FALLBACK_UA = "Mozilla/5.0 (compatible; OroodiBot/1.0; +https://github.com)"
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from extract_offers import USER_AGENT  # noqa: E402
except Exception:  # noqa: BLE001 — السبر يشتغل حتى لو تعذر الاستيراد
    USER_AGENT = _FALLBACK_UA

RIYADH = timezone(timedelta(hours=3))
MAX_BYTES = 5_000_000  # اللقطة المرجعية 2.47MB؛ هامش نمو، والتسجيل يكشف أي بتر

# المرجعية المسجلة قبل التشغيل (كارت t_3c0a6978)
REF_TOTAL_LINKS = 4613
REF_CARDS_OFFERS = 2496
REF_BYTES = 2_472_909
TOLERANCE = 0.05  # ±5%

LOC_RE = re.compile(r"<loc>(.*?)</loc>")
PAIR_RE = re.compile(r"<url>.*?<loc>(.*?)</loc>.*?<lastmod>(.*?)</lastmod>.*?</url>", re.S)


def fetch_raw(url: str) -> dict:
    """سحب خام بنفس رؤوس extract_offers.fetch() — الفرق الوحيد: لا تحويل لنص."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "ar,en;q=0.8"},
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read(MAX_BYTES)
            info = {
                "http_status": r.status,
                "content_type": r.headers.get("Content-Type"),
                "content_length_header": r.headers.get("Content-Length"),
                "final_url": r.url,
                "truncated": len(raw) >= MAX_BYTES,
                "raw": raw,
            }
    except urllib.error.HTTPError as e:
        return {"ok": False, "failure_kind": "HTTP", "failure_reason": f"HTTP {e.code}",
                "exception_type": type(e).__name__}
    except Exception as e:  # noqa: BLE001 — نوع الاستثناء هو قياس السبر نفسه
        return {"ok": False, "failure_kind": "connection", "failure_reason": f"تعذر الاتصال: {type(e).__name__}",
                "exception_type": type(e).__name__, "exception_repr": repr(e)[:300]}
    info["ok"] = True
    info["elapsed_seconds"] = round(time.monotonic() - t0, 1)
    return info


def analyze(raw: bytes, now: datetime) -> dict:
    text = raw.decode("utf-8", errors="replace")
    locs = LOC_RE.findall(text)
    cards = [u for u in locs if "/CardsOffers/" in u]
    cards_en = [u for u in cards if "/en/" in u]
    cards_ar = [u for u in cards if "/en/" not in u]

    pairs = PAIR_RE.findall(text)
    cards_dates = [lm[:10] for u, lm in pairs if "/CardsOffers/" in u and lm]
    distinct = sorted(set(cards_dates))

    def since(days: int) -> int:
        cut = (now - timedelta(days=days)).date().isoformat()
        return sum(1 for d in cards_dates if d >= cut)

    top_date, top_share = None, 0.0
    if cards_dates:
        from collections import Counter
        top_date, n = Counter(cards_dates).most_common(1)[0]
        top_share = round(n / len(cards_dates), 4)

    return {
        "total_links": len(locs),
        "cards_offers_total": len(cards),
        "cards_offers_arabic": len(cards_ar),
        "cards_offers_english_mirror": len(cards_en),
        "cards_with_lastmod": len(cards_dates),
        "cards_distinct_lastmod_dates": len(distinct),
        "cards_lastmod_last_7d": since(7),
        "cards_lastmod_last_14d": since(14),
        "cards_lastmod_last_30d": since(30),
        "cards_top_lastmod_date": top_date,
        "cards_top_lastmod_share": top_share,
        "latest_lastmod": distinct[-1] if distinct else None,
    }


def verdict(fetch_result: dict, metrics: dict | None) -> dict:
    if not fetch_result.get("ok"):
        return {
            "fetch_ok": False,
            "success_criterion_met": False,
            "verdict": "فشل السحب من هذا النطاق — القناة تفضل cron على جهاز البيت فقط",
            "failure_kind": fetch_result.get("failure_kind"),
            "failure_reason": fetch_result.get("failure_reason"),
        }
    cards = metrics["cards_offers_total"]
    within = abs(cards - REF_CARDS_OFFERS) <= REF_CARDS_OFFERS * TOLERANCE
    lo, hi = REF_CARDS_OFFERS * (1 - TOLERANCE), REF_CARDS_OFFERS * (1 + TOLERANCE)
    if within:
        v = (f"مقياس النجاح المسجّل متحقق: HTTP {fetch_result['http_status']} من هذا النطاق "
             f"+ CardsOffers={cards} داخل ±5% من {REF_CARDS_OFFERS} [{lo:.0f}..{hi:.0f}]")
    else:
        v = (f"اتسحب (HTTP {fetch_result['http_status']}) لكن CardsOffers={cards} خارج ±5% "
             f"من {REF_CARDS_OFFERS} [{lo:.0f}..{hi:.0f}] — الفرق يتسجل ويُعرض على المراجعة، لا يُفسَّر تلقائيًا")
    return {"fetch_ok": True, "success_criterion_met": bool(within), "verdict": v}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=SITEMAP_URL)
    ap.add_argument("--out", default="sitemap-probe-results")
    args = ap.parse_args()

    now = datetime.now(RIYADH)
    env = {
        "run_scope": "github_actions" if os.environ.get("GITHUB_RUN_ID") else "local",
        "github_ref": os.environ.get("GITHUB_REF"),
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "github_runner": os.environ.get("RUNNER_NAME"),
        "recorded_at_riyadh": now.strftime("%Y-%m-%d %H:%M:%S +03"),
        "user_agent": USER_AGENT,
        "user_agent_matches_extract_offers": USER_AGENT == _FALLBACK_UA,
        "url": args.url,
    }
    print(f"[سبر sitemap] النطاق: {env['run_scope']} · UA: {USER_AGENT}")

    fr = fetch_raw(args.url)
    raw = fr.pop("raw", None)
    metrics = analyze(raw, now) if raw is not None else None
    v = verdict(fr, metrics)

    result = {"environment": env, "reference": {
        "total_links": REF_TOTAL_LINKS, "cards_offers": REF_CARDS_OFFERS,
        "bytes": REF_BYTES, "tolerance": TOLERANCE,
        "snapshot": "ZEIT-Research/oroodi3/curl_bodies/rajhi_sitemap_20261003_011257.xml",
    }}
    if raw is not None:
        result["fetch"] = {**fr, "downloaded_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        result["metrics"] = metrics
        result["comparison"] = {
            "total_links_delta_vs_ref": metrics["total_links"] - REF_TOTAL_LINKS,
            "cards_offers_delta_vs_ref": metrics["cards_offers_total"] - REF_CARDS_OFFERS,
            "bytes_delta_vs_ref": len(raw) - REF_BYTES,
        }
    else:
        result["fetch"] = fr
    result["verdict"] = v

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if raw is not None:
        (out_dir / "body.xml").write_bytes(raw)

    lines = [f"# سبر sitemap الراجحي — {env['run_scope']}",
             "", f"- الوقت (الرياض): {env['recorded_at_riyadh']}",
             f"- الهوية: {USER_AGENT}"]
    if raw is not None:
        m, c, f = metrics, result["comparison"], result["fetch"]
        lines += [
            f"- HTTP {f['http_status']} · {f['downloaded_bytes']:,} بايت ({c['bytes_delta_vs_ref']:+,} مقابل المرجعية) · {f['elapsed_seconds']} ث · sha256={f['sha256'][:16]}…",
            f"- كل الروابط: {m['total_links']} ({c['total_links_delta_vs_ref']:+,} مقابل {REF_TOTAL_LINKS})",
            f"- CardsOffers: {m['cards_offers_total']} ({c['cards_offers_delta_vs_ref']:+,} مقابل {REF_CARDS_OFFERS}) — عربي {m['cards_offers_arabic']} + مرايا إنجليزية {m['cards_offers_english_mirror']}",
            f"- lastmod (داخل CardsOffers): {m['cards_distinct_lastmod_dates']} تاريخ مختلف · آخر 7 أيام {m['cards_lastmod_last_7d']} · 14 يوم {m['cards_lastmod_last_14d']} · 30 يوم {m['cards_lastmod_last_30d']}",
            f"- أكبر تاريخ جماعي داخل CardsOffers: {m['cards_top_lastmod_date']} ({m['cards_top_lastmod_share']:.1%} من القسم)",
        ]
    else:
        lines += [f"- فشل السحب: {fr.get('failure_kind')} — {fr.get('failure_reason')} ({fr.get('exception_repr', '')})"]
    lines += ["", f"**الحكم:** {v['verdict']}"]
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))

    summary_env = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_env:
        with open(summary_env, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
