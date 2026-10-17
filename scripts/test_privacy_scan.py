"""اختبار فحص الخصوصية: يبني ملفات وهمية وقت التشغيل (لا أسرار محفوظة في المستودع)،
ويتأكد إن الفحص بيفشل على كل نوع، وبيعدّي على مجلد نظيف وعلى ملفات المستودع الحالية.

الاستخدام:  python scripts/test_privacy_scan.py
"""
import random
import string
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import privacy_scan  # noqa: E402

rnd = random.Random(7)


def junk(n: int, alphabet: str = string.ascii_letters + string.digits) -> str:
    return "".join(rnd.choice(alphabet) for _ in range(n))


# كل قيمة وهمية تتجمع من أجزاء وقت التشغيل
FAKES = {
    "win_path.md": "C:" + "\\" + "Us" + "ers\\someone\\project",
    "win_fwd.md": "c:/" + "Us" + "ers/someone/project",
    "bash_path.md": "/c/" + "Us" + "ers/someone/project",
    "sk.txt": "key = " + "s" + "k-" + junk(40),
    "ghp.txt": "token: " + "gh" + "p_" + junk(36),
    "pat.txt": "github" + "_pat_" + junk(40, string.ascii_letters + string.digits + "_"),
    "akia.txt": "AK" + "IA" + junk(16, string.ascii_uppercase + string.digits),
    "aiza.txt": "AI" + "za" + junk(35),
    "email.md": "contact: someone" + "@" + "example" + ".com",
}


def expect(cond: bool, msg: str) -> None:
    print(("  ✅ " if cond else "  ❌ ") + msg)
    if not cond:
        expect.failed = True


expect.failed = False


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # 1) كل نوع لوحده لازم يفشل
        for name, content in FAKES.items():
            case = root / name.replace(".", "_")
            case.mkdir()
            (case / name).write_text(content + "\n", encoding="utf-8")
            expect(len(privacy_scan.scan(case)) == 1, f"يكتشف {name}")
            expect(privacy_scan.main(["--root", str(case)]) == 1, f"يفشل برمز 1 على {name}")

        # 2) ملف .env لازم يفشل حتى لو فاضي، و.env.example مسموح
        env_case = root / "env_case"
        env_case.mkdir()
        (env_case / ".env").write_text("", encoding="utf-8")
        expect(privacy_scan.main(["--root", str(env_case)]) == 1, "يفشل على ملف .env")
        ok_env = root / "env_example"
        ok_env.mkdir()
        (ok_env / ".env.example").write_text("API_KEY=\n", encoding="utf-8")
        expect(privacy_scan.main(["--root", str(ok_env)]) == 0, "يسمح بـ .env.example")

        # 3) مجلد نظيف فيه إيميلات noreply لازم يعدّي
        clean = root / "clean"
        clean.mkdir()
        (clean / "ok.md").write_text(
            "Co-Authored-By: bot <noreply" + "@" + "anthropic.com>\n"
            "41898282+github-actions[bot]" + "@" + "users.noreply.github.com\n"
            "عروض بطاقاتك — scripts/validate.py\n",
            encoding="utf-8",
        )
        expect(privacy_scan.main(["--root", str(clean)]) == 0, "يعدّي على مجلد نظيف")

    # 4) ملفات المستودع الحالية لازم تعدّي
    expect(privacy_scan.main([]) == 0, "يعدّي على ملفات المستودع الحالية")

    # 5) validate.py (اللي بيشتغل في CI مع كل طلب دمج) لازم يفشل لو الفحص لقى مشكلة
    import validate  # noqa: E402
    original = privacy_scan.scan
    try:
        privacy_scan.scan = lambda root=None: ["fake.md:1: مفتاح وهمي"]
        expect(validate.main() == 1, "validate.py يفشل لما فحص الخصوصية يلاقي مشكلة")
    finally:
        privacy_scan.scan = original
    expect(validate.main() == 0, "validate.py يعدّي على ملفات المستودع الحالية")

    if expect.failed:
        print("❌ اختبار فحص الخصوصية فشل")
        return 1
    print("✅ اختبار فحص الخصوصية سليم")
    return 0


if __name__ == "__main__":
    sys.exit(main())
