"""فحص الخصوصية: يمنع دخول أي سر أو مسار محلي أو إيميل شخصي للمستودع العام.

يفحص كل ملف نصي متتبَّع في git (أو كل ملفات مجلد معيّن مع --root)، ويفشل برمز 1 لو لقى:
- مسار مستخدم محلي على ويندوز (بالشرطة المائلة العكسية أو العادية، أو بصيغة Git Bash).
- ملف .env أو .env.<أي شيء> (ما عدا .env.example).
- نمط مفتاح معروف: sk-  ghp_  github_pat_  AKIA  AIza.
- إيميل لا ينتهي بـ noreply (مثل users.noreply.github.com أو noreply@anthropic.com).

الأنماط مبنية من أجزاء عشان الملف ده نفسه ميطلعش في الفحص.
الاستخدام:  python scripts/privacy_scan.py            # الملفات المتتبعة في git
            python scripts/privacy_scan.py --root DIR # كل ملفات مجلد (للاختبار)
لا يطبع القيمة المكتشفة كاملة أبداً، فقط الملف والسطر ونوع المشكلة.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
USERS = "Us" + "ers"

PATTERNS: list[tuple[str, re.Pattern]] = [
    ("مسار محلي (ويندوز)", re.compile(r"\b[A-Za-z]:[\\/]+" + USERS + r"\b", re.I)),
    ("مسار محلي (Git Bash)", re.compile(r"/[a-z]/" + USERS + r"\b", re.I)),
    ("مفتاح sk-", re.compile(r"\b" + "s" + r"k-[A-Za-z0-9_-]{20,}")),
    ("مفتاح ghp_", re.compile(r"\b" + "gh" + r"p_[A-Za-z0-9]{30,}")),
    ("مفتاح github_pat_", re.compile(r"\b" + "github" + r"_pat_[A-Za-z0-9_]{20,}")),
    ("مفتاح AKIA", re.compile(r"\b" + "AK" + r"IA[0-9A-Z]{16}\b")),
    ("مفتاح AIza", re.compile(r"\b" + "AI" + r"za[0-9A-Za-z_-]{30,}")),
]
EMAIL = re.compile(r"[\w.+\-\[\]]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})")


def email_ok(match: re.Match) -> bool:
    text = match.group(0).lower()
    return "noreply" in text or "no-reply" in text


def env_file(path: str) -> bool:
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    return (name == ".env" or name.startswith(".env.")) and name != ".env.example"


def list_files(root: Path | None) -> tuple[Path, list[str]]:
    if root is None:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True)
        return ROOT, [p for p in out.stdout.decode("utf-8").split("\0") if p]
    return root, [p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()]


def scan(root: Path | None = None) -> list[str]:
    base, files = list_files(root)
    problems: list[str] = []
    for rel in files:
        if env_file(rel):
            problems.append(f"{rel}: ملف .env متتبَّع (لا تقرأه، احذفه من git وأضفه لـ .gitignore)")
            continue
        try:
            raw = (base / rel).read_bytes()
        except OSError:
            continue
        if b"\0" in raw[:8192]:
            continue  # ملف ثنائي (صور)
        text = raw.decode("utf-8", errors="replace")
        for n, line in enumerate(text.splitlines(), 1):
            for label, pat in PATTERNS:
                if pat.search(line):
                    problems.append(f"{rel}:{n}: {label}")
            for m in EMAIL.finditer(line):
                if not email_ok(m):
                    problems.append(f"{rel}:{n}: إيميل غير noreply (@{m.group(1)})")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, help="افحص كل ملفات هذا المجلد بدل ملفات git")
    args = ap.parse_args(argv)
    problems = scan(args.root)
    if problems:
        print("❌ فحص الخصوصية فشل:")
        for p in problems:
            print("  -", p)
        return 1
    print("✅ فحص الخصوصية سليم")
    return 0


if __name__ == "__main__":
    sys.exit(main())
