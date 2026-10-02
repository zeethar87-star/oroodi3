"""سبر كثافة السحب — يجيب على سؤال docs/FEASIBILITY.md §3 من داخل GitHub Actions:

لكل صفحة من صفحات البنوك التسعة في جدول الجدوى، يسحبها بنفس fetch() المستخدمة
في extract_offers.py (نفس User-Agent، بلا جافاسكربت، بلا أي مفتاح ذكاء اصطناعي)
ويقيس: عدد أحرف النص، عدد التواريخ الشبيهة، عدد علامات %.

- لا يكتب على offers.json ولا على أي بيانات، ولا يعدّل oroodi_lib.py.
- أي فشل يُسجل بسببه الصريح (HTTP / اتصال / صفحة شبه فارغة) دون كسر بقية الصفحات.
- المخرجات: مجلد نتائج (JSON + CSV + ملخص) يُرفع كـ artifact، وتعليق اختياري
  على بلاغ لو مُرِّر رقمه في مدخلات التشغيل (PROBE_ISSUE_NUMBER).

التشغيل المحلي:  python scripts/probe_run.py --out ../probe-results
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

# نفس دالة السحب حرفيًا: نفس User-Agent ونفس سلوك urllib بلا جافاسكربت
from extract_offers import fetch

FEASIBILITY_PATH = Path(__file__).resolve().parent.parent / "docs" / "FEASIBILITY.md"

# مصدر احتياطي موثق: جدول docs/FEASIBILITY.md §3 (يُستخدم فقط لو تعذّر الاستخراج البرمجي)
FALLBACK_LINKS = [
    ("البنك الأهلي", "https://www.alahli.com/en/pages/personal-banking/credit-cards/credit-card-promotions"),
    ("مصرف الراجحي", "https://www.alrajhibank.com.sa/ar/personal/offers"),
    ("بنك الرياض", "https://www.riyadbank.com/ar/personal-banking/credit-cards/offers"),
    ("الأول (ساب)", "https://www.sab.com/ar/personal/compare-credit-cards/credit-card-special-offers/"),
    ("بنك البلاد", "https://www.bankalbilad.com/ar/personal/cards/offers/Pages/default.aspx"),
    ("البنك العربي الوطني", "https://anb.com.sa/ar/web/anb/all-anb-offers"),
    ("بنك الجزيرة", "https://www.aljazirabank.com.sa/ar-sa/personal/Cards/Offers/Partners-Offers"),
    ("STC Bank", "https://stcbank.com.sa/offers"),
    ("مصرف الإنماء", "https://alinma.com/Media-Campaigns/Stores/alinma-Products-and-Services-Offers/Cashback"),
]

# نمط عدّ التواريخ الشبيهة: ISO (2026-01-31) أو 31/01/2026 أو 31-01-26
DATE_RE = re.compile(r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})\b")


def links_from_feasibility() -> list[tuple[str, str]]:
    """يقرأ روابط §3 من جدول docs/FEASIBILITY.md مباشرة (المزود، الرابط)."""
    text = FEASIBILITY_PATH.read_text(encoding="utf-8")
    m = re.search(r"^##\s*٣.*?(?=^##\s*٤)", text, re.M | re.S)
    if not m:
        return []
    out: list[tuple[str, str]] = []
    for line in m.group(0).splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or set(cells[0]) <= set("-: "):
            continue
        um = re.search(r"https?://[^\s<>\"')\]]+", cells[1])
        if um:
            out.append((cells[0], um.group(0).rstrip(".,،")))
    return out


def probe(targets: list[tuple[str, str]]) -> list[dict]:
    rows = []
    for i, (provider, url) in enumerate(targets, 1):
        print(f"[{i}/{len(targets)}] {provider} …", flush=True)
        t0 = time.monotonic()
        text, err = fetch(url)
        elapsed = round(time.monotonic() - t0, 1)
        if text:
            rows.append({
                "provider": provider, "url": url, "ok": True,
                "chars": len(text), "dates": len(DATE_RE.findall(text)),
                "percent_signs": text.count("%") + text.count("٪"),
                "seconds": elapsed, "failure_reason": None,
            })
        else:
            rows.append({
                "provider": provider, "url": url, "ok": False,
                "chars": 0, "dates": 0, "percent_signs": 0,
                "seconds": elapsed, "failure_reason": err,
            })
    return rows


def write_outputs(out_dir: Path, rows: list[dict], source: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    ok = [r for r in rows if r["ok"]]
    payload = {
        "run_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "links_source": source,
        "total": len(rows),
        "fetched_ok": len(ok),
        "results": rows,
    }
    (out_dir / "results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with (out_dir / "results.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    lines = [
        "# نتيجة سبر كثافة السحب (FEASIBILITY §3)",
        "",
        f"- المصدر: {source}",
        f"- صفحات نُسحبت بنجاح: **{len(ok)} من {len(rows)}**",
        "",
        "| المزود | النتيجة | أحرف | تواريخ | % | ثواني | السبب عند الفشل |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        if r["ok"]:
            res = "نسحبت"
        else:
            res = "فشلت"
        lines.append(f"| {r['provider']} | {res} | {r['chars']} | {r['dates']} | {r['percent_signs']} | {r['seconds']} | {r['failure_reason'] or '—'} |")
    lines += ["", f"قاعدة القرار (§3): أقل من 3 صفحات ← يُفتح قرار Playwright · 3–4 ← مسار (ب) مع لصق يدوي · 5+ ← المسار (ب) كافٍ كما هو."]
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    summary_env = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_env:
        with open(summary_env, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


def comment_on_issue(out_dir: Path) -> None:
    """تعليق الملخص على بلاغ مخصص لو مُرِّر رقمه — بلا أي سر إضافي (github.token)."""
    n = (os.environ.get("PROBE_ISSUE_NUMBER") or "").strip()
    body = (out_dir / "summary.md").read_text(encoding="utf-8")
    if not n:
        print("لا يوجد رقم بلاغ — تم تخطي التعليق.")
        return
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GITHUB_TOKEN"]
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/issues/{n}/comments",
        data=json.dumps({"body": body}).encode(), method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "oroodi3-probe",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"تم التعليق على البلاغ #{n} (HTTP {r.status}).")
    except Exception as e:  # noqa: BLE001
        print(f"تعذر التعليق على البلاغ #{n}: {type(e).__name__} — النتائج محفوظة في الـ artifact.", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="probe-results", help="مجلد مخرجات النتائج")
    args = ap.parse_args()

    targets = links_from_feasibility()
    source = f"جدول {FEASIBILITY_PATH.name} §3 (استخراج برمجي)"
    if len(targets) != 9:
        print(f"الاستخراج البرمجي أعطى {len(targets)} رابطًا — استخدام القائمة الاحتياطية الموثقة.", file=sys.stderr)
        targets = FALLBACK_LINKS
        source = "قائمة احتياطية موثقة من جدول docs/FEASIBILITY.md §3"

    rows = probe(targets)
    out_dir = Path(args.out)
    write_outputs(out_dir, rows, source)
    print((out_dir / "summary.md").read_text(encoding="utf-8"))
    comment_on_issue(out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
