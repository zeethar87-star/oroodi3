"""اختبار fetch() مع ضغط الاستجابة: سيرفر محلي (127.0.0.1) بيرجّع نفس صفحة HTML
مضغوطة gzip أو deflate أو عادية، ومعاها حالة هيدر Content-Encoding ناقص أو غلط.
بعض المواقع (زي صفحة عروض الأهلي) بترجّع gzip حتى لو الطلب ما طلبش ضغط.

الاستخدام:  python scripts/test_fetch_encoding.py
"""
import gzip
import sys
import threading
import zlib
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_offers  # noqa: E402

MARKER = "خصم 20% على بطاقات الأهلي"
HTML = ("<html><body><p>" + (MARKER + " — ") * 20 + "</p></body></html>").encode("utf-8")

# اسم الحالة → (جسم الاستجابة، قيمة Content-Encoding أو None)
CASES = {
    "gzip": (gzip.compress(HTML), "gzip"),
    "deflate": (zlib.compress(HTML), "deflate"),
    "plain": (HTML, None),
    "gzip_missing_header": (gzip.compress(HTML), None),
    "plain_wrong_header": (HTML, "gzip"),
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body, encoding = CASES[self.path.strip("/")]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        if encoding:
            self.send_header("Content-Encoding", encoding)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # كونسول ويندوز الافتراضي ما يطبعش ✅/❌
    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    failed = False
    try:
        for name in CASES:
            text, err = extract_offers.fetch(f"http://127.0.0.1:{server.server_port}/{name}")
            ok = err is None and text is not None and MARKER in text
            print(("  ✅ " if ok else "  ❌ ") + f"{name}: err={err!r}")
            failed |= not ok
    finally:
        server.shutdown()
    print("فشل" if failed else "نجح: fetch بيفك الضغط صح في كل الحالات")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
