#!/usr/bin/env python3
"""Serve only the portfolio page and its generated live-data snapshot."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


REPO = Path(__file__).resolve().parent.parent
ROUTES = {
    "/": (REPO / "index.html", "text/html; charset=utf-8", "no-cache"),
    "/index.html": (REPO / "index.html", "text/html; charset=utf-8", "no-cache"),
    "/data/live_today.json": (
        REPO / "data/live_today.json",
        "application/json; charset=utf-8",
        "no-store",
    ),
}


class PublicHandler(BaseHTTPRequestHandler):
    server_version = "BOTRACE/1.0"

    def do_GET(self):
        self._serve(send_body=True)

    def do_HEAD(self):
        self._serve(send_body=False)

    def _serve(self, *, send_body):
        path = unquote(urlsplit(self.path).path)
        route = ROUTES.get(path)
        if route is None:
            self.send_error(404)
            return

        file_path, content_type, cache_control = route
        try:
            payload = file_path.read_bytes()
        except FileNotFoundError:
            self.send_error(503, "Live asset is not ready")
            return

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", cache_control)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.end_headers()
        if send_body:
            self.wfile.write(payload)


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 8000), PublicHandler)
    print("BOTRACE public server listening on http://127.0.0.1:8000", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
