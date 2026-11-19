#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""极简生产预览服务器：gzip + no-cache + healthz，无第三方依赖。

用法：
    python3 serve.py            # http://127.0.0.1:8000
    PORT=8080 python3 serve.py
"""
import gzip
import mimetypes
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
TEXT_EXT = {".html", ".js", ".css", ".csv", ".json", ".svg", ".txt"}


class Handler(BaseHTTPRequestHandler):
    server_version = "StateFlow/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code, body=b"", ctype="text/plain; charset=utf-8", extra=None, head=False):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def _resolve(self):
        path = unquote(urlparse(self.path).path)
        if path in ("", "/"):
            path = "/index.html"
        fs = os.path.realpath(os.path.join(ROOT, path.lstrip("/")))
        if not (fs == ROOT or fs.startswith(ROOT + os.sep)):
            return None
        return fs

    def do_HEAD(self):
        self.do_GET(head=True)

    def do_GET(self, head=False):
        if urlparse(self.path).path == "/healthz":
            return self._send(200, b"ok\n", "text/plain; charset=utf-8", head=head)

        fs = self._resolve()
        if not fs or not os.path.isfile(fs):
            return self._send(404, b"Not Found\n", "text/plain; charset=utf-8", head=head)

        try:
            with open(fs, "rb") as f:
                body = f.read()
        except OSError:
            return self._send(500, b"Read Error\n", "text/plain; charset=utf-8", head=head)

        ext = os.path.splitext(fs)[1].lower()
        ctype = mimetypes.guess_type(fs)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ext in (".js", ".css", ".svg", ".json"):
            ctype += "; charset=utf-8"

        headers = {}
        if ext in TEXT_EXT or fs.startswith(os.path.join(ROOT, "data")):
            headers["Cache-Control"] = "no-cache, must-revalidate"
        else:
            headers["Cache-Control"] = "public, max-age=86400"
        headers["Vary"] = "Accept-Encoding"

        if ext in TEXT_EXT and "gzip" in self.headers.get("Accept-Encoding", "") and len(body) > 1024:
            body = gzip.compress(body, 6)
            headers["Content-Encoding"] = "gzip"

        self._send(200, body, ctype, headers, head=head)


def main():
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "127.0.0.1")
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"State Flow · http://{host}:{port}  (root: {ROOT})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
