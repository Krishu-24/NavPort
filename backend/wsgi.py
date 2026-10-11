"""WSGI entry point for the NavPort API.

In production gunicorn imports `app` from this module (`gunicorn wsgi:app`, see
`Dockerfile`) and never executes the `__main__` block. Running the file
directly starts the development server instead — that is what `run.bat` and
`run.command` do. Keeping the development conveniences below that guard is
what lets the two share one entry point without the dev server ever being
reachable in a container.
"""

import os
import socket
import sys

from navport import create_app
from navport.config import DEBUG, FRONTEND_PORT, HOST, IS_PRODUCTION, PORT
from navport.telemetry import TELEMETRY, lan_addresses, print_banner

app = create_app()


def _hide_server_version() -> None:
    """Stop the development server announcing its exact Werkzeug and Python
    versions in every response.

    Version disclosure is free reconnaissance: it tells a scanner precisely
    which CVE list to match against. `BaseHTTPRequestHandler` emits this
    header itself, before the app's own `Server` header is applied, so it has
    to be overridden on the handler rather than in an `after_request` hook.
    Gunicorn, used in production, ignores the app's header entirely and writes
    its own; gunicorn.conf.py sets the name it uses.
    """
    try:
        from werkzeug.serving import WSGIRequestHandler
        WSGIRequestHandler.server_version = 'NavPort'
        WSGIRequestHandler.sys_version = ''
    except Exception:
        pass


def port_in_use(port: int) -> bool:
    """True when something is already answering on this port.

    Windows lets a second process bind a port that is already being listened
    on, instead of refusing it. Both processes then appear to start fine while
    the OS quietly routes requests to whichever it likes — so a second server
    looks alive but its console stays empty. Catch that here rather than let it
    become a mystery.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.4)
        return probe.connect_ex(('127.0.0.1', port)) == 0


if __name__ == '__main__':
    # The reloader restarts only the child; re-checking there would trip over
    # the outgoing child's socket during a restart.
    is_reloader_child = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'

    if not is_reloader_child and port_in_use(PORT):
        print(
            f"\n  Something is already listening on port {PORT} - most likely\n"
            f"  NavPort in another window. Close that one first, or use another\n"
            f"  port:\n\n"
            f"      set NAVPORT_PORT=8001 && run.bat\n",
            file=sys.stderr,
        )
        sys.exit(1)

    _hide_server_version()

    owns_console = not DEBUG or is_reloader_child

    if owns_console:
        # Only advertise LAN URLs when we actually bound the LAN. Binding
        # 127.0.0.1 and printing a Network address is how a phone test
        # looks "set up" while every request from another device fails.
        reachable = lan_addresses() if HOST in ('0.0.0.0', '::', '::0') else []  # noqa: S104 - a comparison, not a bind
        print_banner('NavPort', HOST, PORT, reachable, frontend_port=FRONTEND_PORT)

        if IS_PRODUCTION:
            # Reaching here means someone is running the single-threaded
            # development server with production settings, which is a
            # performance and availability problem rather than a security one
            # (the debugger is already off by default). Say so.
            print("  note: this is the development server. In production, run "
                  "gunicorn — see the Dockerfile.\n", file=sys.stderr)

    try:
        app.run(debug=DEBUG, host=HOST, port=PORT, threaded=True)
    except KeyboardInterrupt:
        pass
    finally:
        if owns_console:
            TELEMETRY.print_summary()
