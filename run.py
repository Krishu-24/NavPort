"""Entry point: starts the NavPort Flask development server."""

import os
import socket
import sys

from backend import create_app
from backend.config import DEBUG, HOST, PORT
from backend.telemetry import TELEMETRY, lan_addresses, print_banner

app = create_app()


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
            f"\n  NavPort is already running on port {PORT}.\n"
            f"  Close that window first, or set a different port:\n\n"
            f"      set NAVPORT_PORT=5001 && run.bat        (Windows)\n"
            f"      NAVPORT_PORT=5001 ./run.command         (macOS/Linux)\n",
            file=sys.stderr,
        )
        sys.exit(1)

    owns_console = not DEBUG or is_reloader_child

    if owns_console:
        print_banner('NavPort', HOST, PORT, lan_addresses())

    try:
        app.run(debug=DEBUG, host=HOST, port=PORT)
    except KeyboardInterrupt:
        pass
    finally:
        if owns_console:
            TELEMETRY.print_summary()
