"""The dashboard's toolbox: serve it locally, point it at an API, and turn its
header rules into nginx config.

The dashboard is the static files in ../public. In production Azure Static Web
Apps serves them, and reads the response headers it sends — the
Content-Security-Policy and the rest — from public/staticwebapp.config.json.
That file is the one place those headers are defined. These commands exist so
every other way of serving the dashboard uses it too, instead of keeping a
second copy that drifts:

    python site.py serve                         local development server
    python site.py nginx-config --out DIR        the same rules as nginx config
    python site.py configure --api-base URL      point a deployment at its API

The page's CSP has to name the API it calls, and that address differs per
environment. So the committed config carries a placeholder, __API_ORIGIN__,
which each command fills in for its own environment:

    serve          http://<host the page was loaded from>:8000
    nginx-config   http://$host:8000  (nginx substitutes the request's host)
    configure      the deployed API, e.g. https://navport.<...>.azurecontainerapps.io

Standard library only. This runs on a laptop with nothing but Python, in CI,
and in a throwaway Docker build stage.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

PUBLIC_DIR = Path(__file__).resolve().parent.parent / "public"
CONFIG_NAME = "staticwebapp.config.json"
PLACEHOLDER = "__API_ORIGIN__"
API_PORT = 8000

# Set explicitly rather than taken from the `mimetypes` module. On Windows that
# module reads the registry, where .js is often mapped to text/plain — and a
# browser refuses to run an ES module served as anything but JavaScript, so the
# dashboard would load as a blank page.
TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".webmanifest": "application/manifest+json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".txt": "text/plain; charset=utf-8",
}

# Text-shaped types only. woff2 and the images are already compressed;
# gzipping them again spends CPU to make them slightly bigger.
COMPRESSIBLE = {".html", ".js", ".mjs", ".css", ".json", ".webmanifest", ".svg", ".txt"}
GZIP_MIN_BYTES = 1024


# --------------------------------------------------------------------------
# The rules file
# --------------------------------------------------------------------------

def load_rules(path: Path) -> dict:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def global_headers(rules: dict, api_origin: str, *, https: bool) -> list[tuple[str, str]]:
    """The headers sent on every response, with the API origin filled in.

    HSTS is dropped on plain HTTP: sent from http://localhost it would pin the
    browser to https for that host, which is a nuisance to undo and protects
    nothing.
    """
    headers = []
    for name, value in rules.get("globalHeaders", {}).items():
        if not https and name.lower() == "strict-transport-security":
            continue
        headers.append((name, value.replace(PLACEHOLDER, api_origin)))
    return headers


def route_rules(rules: dict) -> list[tuple[str, dict]]:
    """(route pattern, extra headers) pairs. Static Web Apps allows an exact
    path or a trailing `*` wildcard; those are the two forms supported here."""
    return [(r["route"], r.get("headers", {})) for r in rules.get("routes", []) if r.get("headers")]


def route_matches(pattern: str, path: str) -> bool:
    if pattern.endswith("*"):
        return path.startswith(pattern[:-1])
    return path == pattern


# --------------------------------------------------------------------------
# serve — the local development server
# --------------------------------------------------------------------------

def serve(args: argparse.Namespace) -> int:
    public = PUBLIC_DIR.resolve()
    rules = load_rules(public / CONFIG_NAME)
    types = {**TYPES, **rules.get("mimeTypes", {})}
    quiet = args.quiet

    class Handler(SimpleHTTPRequestHandler):
        server_version = "NavPort-dev"
        sys_version = ""

        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(public), **kw)

        def do_GET(self):
            self._respond(send_body=True)

        def do_HEAD(self):
            self._respond(send_body=False)

        def _api_origin(self) -> str:
            # The API runs on port 8000 of the same machine the page came from:
            # 127.0.0.1 on the laptop, its LAN address from a phone.
            host = urlsplit("//" + (self.headers.get("Host") or "127.0.0.1")).hostname or "127.0.0.1"
            if ":" in host:          # IPv6 literal
                host = f"[{host}]"
            return f"http://{host}:{args.api_port}"

        def _respond(self, send_body: bool):
            # translate_path normalises the URL and drops any '..' segment;
            # the containment check below is a second fence on top of it.
            target = Path(self.translate_path(self.path)).resolve()
            if target.is_dir():
                target = target / "index.html"
            if public not in target.parents or not target.is_file():
                self.send_error(404)
                return

            body = target.read_bytes()
            suffix = target.suffix.lower()
            accepts_gzip = "gzip" in (self.headers.get("Accept-Encoding") or "").lower()
            compressed = suffix in COMPRESSIBLE and accepts_gzip and len(body) >= GZIP_MIN_BYTES
            if compressed:
                body = gzip.compress(body, compresslevel=6, mtime=0)

            self.send_response(200)
            self.send_header("Content-Type", types.get(suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(body)))
            if compressed:
                self.send_header("Content-Encoding", "gzip")
                self.send_header("Vary", "Accept-Encoding")
            for name, value in global_headers(rules, self._api_origin(), https=False):
                self.send_header(name, value)
            url_path = urlsplit(self.path).path
            for pattern, extra in route_rules(rules):
                if route_matches(pattern, url_path):
                    for name, value in extra.items():
                        self.send_header(name, value)
            self.end_headers()
            if send_body:
                self.wfile.write(body)

        def log_message(self, fmt, *a):
            if not quiet:
                super().log_message(fmt, *a)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    if not quiet:
        print(f"Serving {public} on http://{args.host}:{args.port}/  (API expected on port {args.api_port})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


# --------------------------------------------------------------------------
# nginx-config — the same rules for the local Docker image
# --------------------------------------------------------------------------

def _nginx_quote(value: str) -> str:
    # `$host` must survive as an nginx variable; nothing else in these values
    # uses `$`, and double quotes are the only other character needing escape.
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def nginx_config(args: argparse.Namespace) -> int:
    rules = load_rules(Path(args.config))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # nginx substitutes the request's Host (without port) for $host, giving the
    # same "API on port 8000 of this machine" rule as the dev server.
    headers = global_headers(rules, f"http://$host:{args.api_port}", https=False)
    header_lines = [f"add_header {name} {_nginx_quote(value)} always;" for name, value in headers]
    (out / "headers.conf").write_text(
        "# Generated from staticwebapp.config.json by tools/site.py - do not edit.\n"
        + "\n".join(header_lines) + "\n",
        encoding="utf-8",
    )

    # An add_header inside a location switches off inheritance of the
    # server-level ones, so every generated location re-includes them.
    include = f"include {args.include_dir.rstrip('/')}/headers.conf;"
    blocks = ["# Generated from staticwebapp.config.json by tools/site.py - do not edit."]
    for pattern, extra in route_rules(rules):
        if pattern.endswith("*"):
            match = f"^~ {pattern[:-1]}"
        elif "*" in pattern:
            print(f"unsupported route pattern for nginx: {pattern}", file=sys.stderr)
            return 1
        else:
            match = f"= {pattern}"
        lines = [f"location {match} {{", f"    {include}"]
        lines += [f"    add_header {name} {_nginx_quote(value)} always;" for name, value in extra.items()]
        lines.append("}")
        blocks.append("\n".join(lines))
    for ext, mime in rules.get("mimeTypes", {}).items():
        blocks.append("\n".join([
            f"location ~* \\{ext}$ {{",
            f"    {include}",
            "    types { }",
            f"    default_type {mime};",
            "}",
        ]))
    (out / "routes.conf").write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    print(f"wrote {out / 'headers.conf'} and {out / 'routes.conf'}")
    return 0


# --------------------------------------------------------------------------
# configure — point a deployment at its API
# --------------------------------------------------------------------------

API_CONFIG_TEMPLATE = """\
/**
 * Where the dashboard finds the NavPort API — generated for this deployment
 * by frontend/tools/site.py. The committed copy of this file is the local
 * development default; see it for the full explanation.
 */
if (!window.NAVPORT_API_BASE) {{
    window.NAVPORT_API_BASE = {base};
}}
"""


def _validated_base(raw: str) -> tuple[str, str]:
    """(base without trailing slash, origin). Refuses anything that isn't a
    plain absolute http(s) URL: credentials, a query string or a fragment in
    an API address is always a mistake, and would be baked into a public file."""
    parts = urlsplit(raw.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(f"not an absolute http(s) URL: {raw!r}")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError(f"API base must not carry credentials, a query or a fragment: {raw!r}")
    origin = f"{parts.scheme}://{parts.netloc}"
    return (origin + parts.path).rstrip("/"), origin


def configure(args: argparse.Namespace) -> int:
    public = Path(args.public)
    try:
        base, origin = _validated_base(args.api_base)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    config_path = public / CONFIG_NAME
    text = config_path.read_text(encoding="utf-8")
    if PLACEHOLDER not in text:
        print(f"error: {PLACEHOLDER} not found in {config_path} - already configured?", file=sys.stderr)
        return 1
    config_path.write_text(text.replace(PLACEHOLDER, origin), encoding="utf-8")

    (public / "js" / "api-config.js").write_text(
        API_CONFIG_TEMPLATE.format(base=json.dumps(base)), encoding="utf-8"
    )
    print(f"configured {public} for API {base} (CSP connect-src now allows {origin})")
    return 0


# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("serve", help="serve public/ for local development")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--api-port", type=int, default=API_PORT)
    p.add_argument("--quiet", action="store_true", help="don't log each request")
    p.set_defaults(func=serve)

    p = sub.add_parser("nginx-config", help="write nginx include files from the rules")
    p.add_argument("--config", default=str(PUBLIC_DIR / CONFIG_NAME))
    p.add_argument("--out", required=True, help="directory to write headers.conf and routes.conf into")
    p.add_argument("--include-dir", default="/etc/nginx/navport",
                   help="where nginx will find headers.conf at runtime")
    p.add_argument("--api-port", type=int, default=API_PORT)
    p.set_defaults(func=nginx_config)

    p = sub.add_parser("configure", help="point public/ at a deployed API (CI, before deploying)")
    p.add_argument("--api-base", required=True, help="e.g. https://navport.<...>.azurecontainerapps.io")
    p.add_argument("--public", default=str(PUBLIC_DIR))
    p.set_defaults(func=configure)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
