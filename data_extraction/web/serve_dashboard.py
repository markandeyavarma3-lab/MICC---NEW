#!/usr/bin/env python3
"""serve_dashboard.py — minimal authenticated web layer for the MICC dashboard.

Stdlib only (no Flask). Serves MICC_dashboard.html behind HTTP Basic Auth, with a
/refresh route that regenerates the live signals + deals/F&O intel + dashboard.

Credentials via env (defaults for local use):  MICC_USER (admin) / MICC_PASS (micc).
Port via MICC_PORT (8765).

Run:  py -3.14 web/serve_dashboard.py
Then open http://localhost:8765  (login admin/micc — change via env for anything shared).
"""
import base64
import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import api  # noqa: E402  (web/api.py — JSON REST endpoints)

ROOT = Path(__file__).resolve().parents[1]          # data_extraction/
DASH = Path(r"D:\MICC\MICC_dashboard.html")
USER = os.getenv("MICC_USER", "admin")
PASS = os.getenv("MICC_PASS", "micc")
PORT = int(os.getenv("MICC_PORT", "8765"))
REFRESH = ["common/generate_signals.py", "common/build_market_intel.py",
           "common/build_dashboard.py"]


class Handler(BaseHTTPRequestHandler):
    def _authed(self):
        h = self.headers.get("Authorization", "")
        if not h.startswith("Basic "):
            return False
        try:
            u, p = base64.b64decode(h[6:]).decode("utf-8").split(":", 1)
        except Exception:
            return False
        return u == USER and p == PASS

    def _deny(self):
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="MICC"')
        self.end_headers()
        self.wfile.write(b"Authentication required")

    def _refresh(self):
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        for s in REFRESH:
            subprocess.run([sys.executable, str(ROOT / s)], cwd=str(ROOT),
                           env=env, capture_output=True)

    def do_GET(self):
        if not self._authed():
            return self._deny()
        if self.path.startswith("/health"):
            self.send_response(200); self.end_headers(); self.wfile.write(b"ok"); return
        if self.path.startswith("/api"):
            status, obj = api.handle(self.path.split("?")[0])
            body = json.dumps(obj, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith("/slides"):
            f = Path(r"D:\MICC\MICC_slides.html")
            if f.exists():
                data = f.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers(); self.wfile.write(data); return
            self.send_response(404); self.end_headers(); return
        if self.path.startswith("/refresh"):
            self._refresh()
            self.send_response(303); self.send_header("Location", "/"); self.end_headers(); return
        if not DASH.exists():
            self._refresh()
        data = DASH.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def main():
    print(f"MICC dashboard -> http://localhost:{PORT}   (user={USER}; /refresh to rebuild)",
          flush=True)
    if USER == "admin" and PASS == "micc":
        print("  WARNING: default credentials — set MICC_USER / MICC_PASS before sharing.", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
