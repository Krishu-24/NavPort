"""Live console telemetry: who is connected, what they asked for, how much
data went back. Pure stdlib — no extra dependencies, no effect on responses.

Rendering degrades gracefully: colour is dropped when the output is piped to a
file, when NO_COLOR is set, or when the terminal can't do ANSI.
"""

import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# ANSI
# ---------------------------------------------------------------------------


def _supports_colour() -> bool:
    if os.environ.get('NO_COLOR'):
        return False
    if not sys.stdout.isatty():
        return False
    if os.name == 'nt':
        # Ask the console for VT processing; older cmd.exe will refuse.
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)          # STD_OUTPUT_HANDLE
            mode = ctypes.c_ulong()
            if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                return False
            return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
        except Exception:
            return False
    return True


COLOUR = _supports_colour()


def _prepare_stream() -> bool:
    """Windows pipes default to cp1252, which cannot encode box-drawing glyphs.
    Ask for UTF-8; report whether the stream can actually carry the fancy set."""
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

    probe = '─●·→'
    encoding = getattr(sys.stdout, 'encoding', None) or 'ascii'
    try:
        probe.encode(encoding)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


UNICODE_OK = _prepare_stream()

# Every glyph the renderer uses, with an ASCII fallback for dumb terminals.
G = {
    'tl': '┌', 'tr': '┐', 'bl': '└', 'br': '┘',
    'ml': '├', 'mr': '┤', 'h': '─', 'v': '│',
    'dot': '●', 'mid': '·', 'arrow': '→',
} if UNICODE_OK else {
    'tl': '+', 'tr': '+', 'bl': '+', 'br': '+',
    'ml': '+', 'mr': '+', 'h': '-', 'v': '|',
    'dot': '*', 'mid': '-', 'arrow': '->',
}


SEP = f"  {G['mid']}  "


def _c(code: str) -> str:
    return f"\033[{code}m" if COLOUR else ''


RESET = _c('0')
DIM = _c('2')
BOLD = _c('1')
GREY = _c('38;5;244')
FAINT = _c('38;5;239')
CYAN = _c('38;5;80')
BLUE = _c('38;5;75')
GREEN = _c('38;5;72')
AMBER = _c('38;5;179')
RED = _c('38;5;167')
MAGENTA = _c('38;5;140')
WHITE = _c('38;5;253')


def _visible_len(text: str) -> int:
    return len(re.sub(r'\033\[[0-9;]*m', '', text))


# ---------------------------------------------------------------------------
# User-Agent parsing (regex, same spirit as the METAR decoder)
# ---------------------------------------------------------------------------

_BROWSERS = [
    ('Edge',     re.compile(r'Edg(?:e|A|iOS)?/(\d+)')),
    ('Opera',    re.compile(r'OPR/(\d+)')),
    ('Samsung',  re.compile(r'SamsungBrowser/(\d+)')),
    ('Firefox',  re.compile(r'Firefox/(\d+)')),
    ('Chrome',   re.compile(r'Chrome/(\d+)')),
    ('Safari',   re.compile(r'Version/(\d+).*Safari')),
    ('curl',     re.compile(r'curl/([\d.]+)')),
    ('Python',   re.compile(r'python-requests/([\d.]+)')),
]

_OS = [
    ('Windows 11/10', re.compile(r'Windows NT 10\.0')),
    ('Windows 8.1',   re.compile(r'Windows NT 6\.3')),
    ('Windows 7',     re.compile(r'Windows NT 6\.1')),
    ('iPadOS',        re.compile(r'iPad')),
    ('iOS',           re.compile(r'iPhone|iPod')),
    ('Android',       re.compile(r'Android (\d+)')),
    ('macOS',         re.compile(r'Mac OS X')),
    ('ChromeOS',      re.compile(r'CrOS')),
    ('Linux',         re.compile(r'Linux|X11')),
]


def parse_user_agent(ua: str) -> Dict[str, str]:
    """Best-effort browser / OS / form-factor from a User-Agent string."""
    if not ua:
        return {'browser': 'Unknown', 'os': 'Unknown', 'device': 'Unknown'}

    browser = 'Unknown'
    for name, pattern in _BROWSERS:
        if m := pattern.search(ua):
            browser = f"{name} {m.group(1)}" if m.groups() else name
            break

    operating_system = 'Unknown'
    for name, pattern in _OS:
        if m := pattern.search(ua):
            operating_system = f"Android {m.group(1)}" if name == 'Android' and m.groups() else name
            break

    if re.search(r'iPad|Tablet', ua):
        device = 'Tablet'
    elif re.search(r'Mobi|iPhone|Android.*Mobile', ua):
        device = 'Mobile'
    elif browser in ('curl', 'Python') or browser.startswith(('curl', 'Python')):
        device = 'CLI'
    else:
        device = 'Desktop'

    return {'browser': browser, 'os': operating_system, 'device': device}


def human_bytes(n: float) -> str:
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f"{n:.0f} {unit}" if unit == 'B' else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def human_ms(ms: float) -> str:
    return f"{ms:.0f} ms" if ms < 1000 else f"{ms / 1000:.2f} s"


def human_uptime(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds // 60:.0f}m {seconds % 60:.0f}s"
    hours, rest = divmod(seconds, 3600)
    return f"{hours:.0f}h {rest // 60:.0f}m"


def plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@dataclass
class Device:
    key: str
    ip: str
    browser: str
    os: str
    device: str
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    requests: int = 0
    bytes_out: int = 0

    @property
    def label(self) -> str:
        return f"{self.browser}{SEP}{self.os}{SEP}{self.device}"


class Telemetry:
    """Thread-safe counters for the dev server console."""

    SUMMARY_EVERY = 20.0      # seconds between traffic panels

    def __init__(self):
        self.devices: Dict[str, Device] = {}
        self.requests = 0
        self.bytes_out = 0
        self.started = time.time()
        self._lock = Lock()
        # Start the clock now so the first request doesn't trigger a panel.
        self._last_summary = time.time()

    # -- recording ---------------------------------------------------------

    def record(self, *, ip: str, ua: str, method: str, path: str,
               status: int, size: int, ms: float) -> None:
        info = parse_user_agent(ua)
        key = f"{ip}|{info['browser']}|{info['os']}"

        with self._lock:
            device = self.devices.get(key)
            is_new = device is None

            if is_new:
                device = Device(key=key, ip=ip, **info)
                self.devices[key] = device

            device.last_seen = time.time()
            device.requests += 1
            device.bytes_out += size

            self.requests += 1
            self.bytes_out += size

            due = (time.time() - self._last_summary) > self.SUMMARY_EVERY
            if due:
                self._last_summary = time.time()

        if is_new:
            self._print_new_device(device)

        self._print_request(method, path, status, size, ms, device)

        if due:
            self.print_summary()

    # -- rendering ---------------------------------------------------------

    def _print_request(self, method, path, status, size, ms, device) -> None:
        colour = GREEN if status < 300 else AMBER if status < 400 else RED
        is_asset = bool(re.search(r'\.(css|js|png|ico|svg|woff2?|map)$', path))
        tone = FAINT if is_asset else WHITE

        if len(path) > 34:
            path = path[:31] + '…'

        line = (
            f"  {FAINT}{datetime.now().strftime('%H:%M:%S')}{RESET} "
            f"{CYAN if not is_asset else FAINT}{method:<5}{RESET}"
            f"{tone}{path:<35}{RESET}"
            f"{colour}{status}{RESET}  "
            f"{GREY}{human_bytes(size):>9}{RESET}  "
            f"{GREY}{human_ms(ms):>7}{RESET}  "
            f"{FAINT}{device.browser}/{device.device}{RESET}"
        )
        print(line, flush=True)

    def _print_new_device(self, device: Device) -> None:
        print(
            f"\n  {GREEN}{G['dot']}{RESET} {BOLD}device connected{RESET}  "
            f"{WHITE}{device.ip}{RESET}  {GREY}{device.label}{RESET}",
            flush=True,
        )

    def print_summary(self) -> None:
        with self._lock:
            devices = sorted(self.devices.values(), key=lambda d: -d.requests)
            requests, bytes_out = self.requests, self.bytes_out

        if not devices:
            return

        width = min(shutil.get_terminal_size((96, 24)).columns - 2, 96)
        uptime = time.time() - self.started

        sep = f"{GREY}{SEP}{RESET}"
        head = (
            f"{BOLD}Traffic{RESET}{sep}"
            f"{WHITE}{len(devices)}{RESET}{GREY} {'device' if len(devices) == 1 else 'devices'}{RESET}{sep}"
            f"{WHITE}{requests}{RESET}{GREY} {'request' if requests == 1 else 'requests'}{RESET}{sep}"
            f"{WHITE}{human_bytes(bytes_out)}{RESET}{GREY} sent{RESET}{sep}"
            f"{GREY}up {human_uptime(uptime)}{RESET}"
        )

        print(f"\n{GREY}{G['tl']}{G['h'] * (width - 2)}{G['tr']}{RESET}")
        print(f"{GREY}{G['v']}{RESET} {head}{' ' * max(0, width - 4 - _visible_len(head))} {GREY}{G['v']}{RESET}")
        print(f"{GREY}{G['ml']}{G['h'] * (width - 2)}{G['mr']}{RESET}")

        for d in devices[:8]:
            idle = time.time() - d.last_seen
            dot = GREEN if idle < 60 else FAINT
            row = (
                f"{dot}{G['dot']}{RESET} {WHITE}{d.ip:<15}{RESET} "
                f"{GREY}{d.browser:<12}{RESET}"
                f"{GREY}{d.os:<15}{RESET}"
                f"{GREY}{d.device:<8}{RESET}"
                f"{BLUE}{d.requests:>5}{RESET}{GREY} req{RESET}  "
                f"{MAGENTA}{human_bytes(d.bytes_out):>9}{RESET}"
            )
            print(f"{GREY}{G['v']}{RESET} {row}{' ' * max(0, width - 4 - _visible_len(row))} {GREY}{G['v']}{RESET}")

        print(f"{GREY}{G['bl']}{G['h'] * (width - 2)}{G['br']}{RESET}\n", flush=True)


TELEMETRY = Telemetry()


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------


def print_banner(app_name: str, host: str, port: int, lan_ips=None) -> None:
    width = min(shutil.get_terminal_size((96, 24)).columns - 2, 72)
    if isinstance(lan_ips, str):
        lan_ips = [lan_ips]
    lan_ips = lan_ips or []

    # One address per destination. There is a single UI now, so the only
    # distinction worth drawing is which machines can reach a given address.
    rows = [
        (f"{BOLD}{WHITE}{app_name}{RESET}", ''),
        ('', ''),
    ]

    if lan_ips:
        ip = lan_ips[0]
        rows += [
            (f"{GREEN}Open{RESET}",    f"{GREEN}http://{ip}:{port}/{RESET}"),
            (f"{GREY}This PC{RESET}",  f"{CYAN}http://127.0.0.1:{port}/{RESET}"),
            ('', ''),
            (f"{FAINT}The first opens on this laptop and on any phone{RESET}", ''),
            (f"{FAINT}on the same Wi-Fi - one server, one address.{RESET}", ''),
            (f"{FAINT}127.0.0.1 only ever means \"the machine asking\",{RESET}", ''),
            (f"{FAINT}so a phone can never open that one.{RESET}", ''),
        ]
    else:
        rows += [
            (f"{GREEN}Open{RESET}", f"{GREEN}http://127.0.0.1:{port}/{RESET}"),
            ('', ''),
            (f"{FAINT}Listening on this machine only, so there is no{RESET}", ''),
            (f"{FAINT}phone address. For one, start it with:{RESET}", ''),
            (f"{FAINT}  set NAVPORT_HOST=0.0.0.0 && run.bat{RESET}", ''),
        ]

    print(f"\n{GREY}{G['tl']}{G['h'] * (width - 2)}{G['tr']}{RESET}")
    for left, right in rows:
        text = left if not right else f"{left:<{10 + (len(left) - _visible_len(left))}}{right}"
        print(f"{GREY}{G['v']}{RESET} {text}{' ' * max(0, width - 4 - _visible_len(text))} {GREY}{G['v']}{RESET}")
    print(f"{GREY}{G['bl']}{G['h'] * (width - 2)}{G['br']}{RESET}")
    print(f"{FAINT}  ctrl+c to stop{RESET}\n", flush=True)


def lan_addresses() -> List[str]:
    """Every IPv4 address this machine answers on, primary route first.

    One address isn't enough: with a mobile hotspot running, the laptop is on
    two networks at once, and the address other devices need is the hotspot's
    (typically 192.168.137.1) — not the one carrying the default route.
    """
    import socket

    found: List[str] = []

    # The default-route address, via a UDP socket that never sends anything.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.2)
            s.connect(('10.255.255.255', 1))
            found.append(s.getsockname()[0])
    except Exception:
        pass

    # Everything else bound to this host.
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = info[4][0]
            if address not in found and not address.startswith(('127.', '169.254.')):
                found.append(address)
    except Exception:
        pass

    return found


def lan_address() -> Optional[str]:
    """Primary LAN IP, or None when the machine has no network address."""
    addresses = lan_addresses()
    return addresses[0] if addresses else None


# ---------------------------------------------------------------------------
# Flask wiring
# ---------------------------------------------------------------------------


def install_telemetry(app) -> None:
    """Attach request timing + console reporting to a Flask app."""
    from flask import g, request

    @app.before_request
    def _start_timer():
        g._telemetry_start = time.perf_counter()

    @app.after_request
    def _report(response):
        started = getattr(g, '_telemetry_start', None)
        ms = (time.perf_counter() - started) * 1000 if started else 0.0

        # Prefer the header: static files are sent in direct_passthrough mode,
        # where calculate_content_length() returns None. Never touch the body
        # itself — that would break streamed/passthrough responses.
        size = response.content_length
        if size is None:
            size = response.calculate_content_length() or 0

        # Reporting must never be able to fail a request — a console that
        # can't encode a glyph shouldn't turn a 200 into a 500.
        try:
            TELEMETRY.record(
                ip=request.headers.get('X-Forwarded-For', request.remote_addr or '-').split(',')[0].strip(),
                ua=request.headers.get('User-Agent', ''),
                method=request.method,
                path=request.path,
                status=response.status_code,
                size=size,
                ms=ms,
            )
        except Exception as exc:                                  # pragma: no cover
            print(f"  [telemetry] suppressed: {exc!r}", flush=True)

        return response
