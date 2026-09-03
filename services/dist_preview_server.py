#!/usr/bin/env python3
import argparse
import http.server
import mimetypes
import os
import re
import socketserver
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import ProxyHandler, Request, build_opener


OLD_API_BASES = (
    "https://10.73.56.38:8444",
    "http://10.73.56.38:8081",
)


def rewrite_frontend_js(text, api_base):
    for old in OLD_API_BASES:
        text = text.replace(old, api_base)

    # The bundled chart pages often pass values like "605.71" to ECharts after
    # formatting them with toFixed(2). Keep table/export formatting intact where
    # possible, but make chart series data numeric so value axes render reliably.
    return re.sub(r"parseFloat\(([^()]+)\)\.toFixed\(2\)", r"Number.parseFloat(\1)", text)


class DistPreviewHandler(http.server.SimpleHTTPRequestHandler):
    dist_dir: Path
    api_opener = build_opener(ProxyHandler({}))
    forbidden_path = "__forbidden_path__"

    def translate_path(self, path):
        parsed = urlparse(path)
        rel = unquote(parsed.path).lstrip("/")
        target = (self.dist_dir / rel).resolve()
        try:
            target.relative_to(self.dist_dir)
        except ValueError:
            return str(self.dist_dir / self.forbidden_path)
        return str(target)

    def list_directory(self, path):
        """Do not expose file names when a directory is requested."""
        self.send_error(404, "Directory listing is disabled")
        return None

    def do_GET(self):
        path = Path(self.translate_path(self.path))
        parsed_path = urlparse(self.path).path

        if parsed_path.startswith("/api/"):
            self.proxy_api_request()
            return

        if path == self.dist_dir / self.forbidden_path:
            self.send_error(404, "Not found")
            return

        if path.is_file() and path.suffix == ".js":
            self.send_rewritten_js(path)
            return

        if not path.exists() and "." not in parsed_path.rsplit("/", 1)[-1]:
            self.path = "/index.html"

        super().do_GET()

    def send_rewritten_js(self, path):
        text = rewrite_frontend_js(path.read_text(encoding="utf-8"), "")
        body = text.encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(str(path))[0] or "application/javascript")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def proxy_api_request(self):
        target = f"http://127.0.0.1:8081{self.path}"
        try:
            req = Request(target, headers={"Accept": self.headers.get("Accept", "application/json")})
            with self.api_opener.open(req, timeout=15) as response:
                body = response.read()
                self.send_response(response.status)
                self.send_header("Content-Type", response.headers.get("Content-Type", "application/json"))
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
        except Exception as exc:
            body = (f'{{"error":"API proxy failed: {str(exc)}"}}').encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def main():
    parser = argparse.ArgumentParser(description="Serve the built frontend with current-host API rewriting.")
    parser.add_argument("--dist", required=True)
    parser.add_argument("--port", type=int, default=8089)
    args = parser.parse_args()

    dist_dir = Path(args.dist).resolve()
    if not (dist_dir / "index.html").exists():
        raise SystemExit(f"index.html not found in {dist_dir}")

    DistPreviewHandler.dist_dir = dist_dir
    os.chdir(dist_dir)

    with ReusableTCPServer(("0.0.0.0", args.port), DistPreviewHandler) as httpd:
        print(f"Serving dist preview at http://0.0.0.0:{args.port}")
        print(f"Dist dir: {dist_dir}")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
