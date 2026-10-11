"""Run NavPort locally: the dashboard and the API, side by side.

Production runs these as two separate Azure services. This runs them as two
local servers on one machine — the dashboard on 8080, the API on 8000 — so the
browser sees the same cross-origin arrangement it gets in production.

`run.bat` and `run.command` call this once Python and the dependencies are
ready. Ctrl+C stops both.

    python scripts/dev.py
"""

from __future__ import annotations

import importlib.util
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API_ENTRY = ROOT / "backend" / "wsgi.py"
SITE_TOOL = ROOT / "frontend" / "tools" / "site.py"


def port_in_use(port: int) -> bool:
    """Windows lets a second process bind a port that's already being listened
    on, and then routes requests to whichever it likes — so check first rather
    than end up with two servers and a confusing half of the traffic."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.4)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def load_site_tool():
    spec = importlib.util.spec_from_file_location("navport_site", SITE_TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    api_port = int(os.environ.get("NAVPORT_PORT", 8000))
    web_port = int(os.environ.get("NAVPORT_FRONTEND_PORT", 8080))
    host = os.environ.get("NAVPORT_HOST", "127.0.0.1")

    if port_in_use(web_port):
        print(f"\n  Something is already listening on port {web_port} - most likely\n"
              f"  NavPort in another window. Close that one first.\n", file=sys.stderr)
        return 1

    # The dashboard runs as a thread of this process, so it can never be left
    # running after the API has stopped. Request logging is off: the API's
    # console telemetry is the useful view, and every CSS file isn't.
    site = load_site_tool()
    web = threading.Thread(
        target=site.main,
        args=(["serve", "--host", host, "--port", str(web_port),
               "--api-port", str(api_port), "--quiet"],),
        daemon=True,
    )
    web.start()

    # The API runs exactly as `python backend/wsgi.py` would, in its own
    # process, so the development server's auto-reload and the console
    # telemetry behave normally. It prints the banner with both addresses.
    env = {**os.environ, "NAVPORT_PORT": str(api_port), "NAVPORT_FRONTEND_PORT": str(web_port)}
    api = subprocess.Popen([sys.executable, str(API_ENTRY)], env=env)

    try:
        return api.wait()
    except KeyboardInterrupt:
        # The console delivered the same Ctrl+C to the API, which is now
        # printing its session summary. Give it a moment to finish rather than
        # cutting it off mid-line, then make sure it's gone.
        try:
            return api.wait(timeout=5)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            api.terminate()
            return 0


if __name__ == "__main__":
    sys.exit(main())
