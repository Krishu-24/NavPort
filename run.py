"""Entry point: starts the NavPort Flask development server."""

import os

from backend import create_app
from backend.config import DEBUG, HOST, PORT
from backend.telemetry import TELEMETRY, lan_address, print_banner

app = create_app()

if __name__ == '__main__':
    # With the reloader on, the parent process only watches files — let the
    # child that actually serves requests own the console.
    owns_console = not DEBUG or os.environ.get('WERKZEUG_RUN_MAIN') == 'true'

    if owns_console:
        print_banner('NavPort', HOST, PORT, lan_address())

    try:
        app.run(debug=DEBUG, host=HOST, port=PORT)
    except KeyboardInterrupt:
        pass
    finally:
        if owns_console:
            TELEMETRY.print_summary()
