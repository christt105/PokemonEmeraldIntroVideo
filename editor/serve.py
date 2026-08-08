#!/usr/bin/env python3
"""Local server for the scene editor.

Serves the project directory so the editor can read the exported sprites, and
adds two endpoints so you never have to leave the browser:

  POST /api/save    {"name": "wide", "scene": {...}}  -> writes scenes/wide.json
  POST /api/render  {"name": "wide", "step": 2}       -> runs compose.py

Binds to localhost only. Both endpoints refuse anything that would write or
read outside scenes/.

  python3 editor/serve.py     then open http://127.0.0.1:8777/editor/
"""

import json
import os
import re
import subprocess
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENES = os.path.join(ROOT, "scenes")
SAFE_NAME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, fmt, *args):
        if "/api/" in (self.path or ""):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path not in ("/api/save", "/api/render"):
            return self._json(404, {"error": "unknown endpoint"})

        length = int(self.headers.get("Content-Length") or 0)
        if length > 1 << 20:
            return self._json(413, {"error": "payload too large"})
        try:
            req = json.loads(self.rfile.read(length) or b"{}")
        except ValueError as exc:
            return self._json(400, {"error": f"bad JSON: {exc}"})

        name = str(req.get("name", ""))
        if not SAFE_NAME.match(name):
            return self._json(400, {"error": "name must be [A-Za-z0-9_-]"})
        path = os.path.join(SCENES, name + ".json")

        if self.path == "/api/save":
            scene = req.get("scene")
            if not isinstance(scene, dict):
                return self._json(400, {"error": "scene must be an object"})
            os.makedirs(SCENES, exist_ok=True)
            with open(path, "w") as fh:
                json.dump(scene, fh, indent=2, ensure_ascii=False)
            return self._json(200, {"saved": os.path.relpath(path, ROOT)})

        if not os.path.exists(path):
            return self._json(404, {"error": "save the scene first"})
        step = req.get("step", 2)
        step = step if isinstance(step, int) and 1 <= step <= 16 else 2
        fmt = "mp4" if req.get("format") == "mp4" else "gif"
        try:
            proc = subprocess.run(
                [sys.executable, "compose.py", os.path.relpath(path, ROOT),
                 "--format", fmt, "--step", str(step), "--out", "out"],
                cwd=ROOT, capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            return self._json(504, {"error": "render timed out"})
        if proc.returncode:
            return self._json(500, {"error": proc.stderr.strip() or "render failed"})
        return self._json(200, {"output": proc.stdout.strip(),
                                "file": f"out/{name}.{fmt}"})


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8777
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"scene editor: http://127.0.0.1:{port}/editor/")
    print(f"serving {ROOT}   (ctrl-c to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
