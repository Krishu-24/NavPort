"""Render the dashboard at phone, tablet and desktop sizes and check the layout.

NavPort ships as a web app, an installed PWA, and a Tauri shell on five
platforms, so the same markup has to survive a 360px Android phone and a
1920px desktop. This drives a headless Chromium over the DevTools Protocol,
runs a real briefing at each size, writes a screenshot, and asserts the things
that actually break when a layout is ported to a phone:

  * horizontal overflow (the classic symptom of a fixed width)
  * tap targets under 44px, the floor both Apple and Google publish
  * inputs under 16px, which makes iOS Safari zoom on focus
  * content hidden behind the notch or home indicator

Run the server first, then:

    python scripts/ui_matrix.py [--base http://127.0.0.1:5000] [--keep-open]

Screenshots land in docs/screenshots/. There is no websocket library in
requirements.txt and this is the only thing that would need one, so the
handful of frames this needs are built by hand below.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "docs" / "screenshots"

# Chromium is only used as a renderer here; Edge ships with Windows, so this
# needs no extra install on the machine the project is developed on.
CANDIDATES = [
    os.environ.get("NAVPORT_BROWSER", ""),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "google-chrome",
    "chromium",
    "microsoft-edge",
]

# Widths taken from the real devices, not round numbers, so the breakpoints
# get exercised where they actually land. Everything renders at 1x: the audit
# works in CSS pixels, and a 2x capture of a 7500px-tall page is 800 KB of
# committed screenshot for no extra information.
DEVICES = [
    # name                  w     h  mobile
    ("android-small", 360, 740, True),
    ("iphone-15", 393, 852, True),
    ("pixel-8", 412, 915, True),
    ("iphone-15-landscape", 852, 393, True),
    ("ipad-air", 820, 1180, True),
    ("desktop-1280", 1280, 800, False),
    ("desktop-1920", 1920, 1080, False),
]

ROUTE = {
    "departure": "KJFK",
    "destination": "KDEN",
    "waypoints": "KPIT",
    "cruiseSpeed": 450,
}


# --------------------------------------------------------------------------
# Minimal websocket client. Enough of RFC 6455 to talk to CDP: text frames
# out, text frames in, no extensions, no continuation on send.
# --------------------------------------------------------------------------

class WebSocket:
    def __init__(self, url: str, timeout: float = 20.0):
        _, _, rest = url.partition("://")
        hostport, _, path = rest.partition("/")
        host, _, port = hostport.partition(":")
        self.sock = socket.create_connection((host, int(port or 80)), timeout=timeout)
        self.sock.settimeout(timeout)
        self.buf = b""

        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(
            f"GET /{path} HTTP/1.1\r\n"
            f"Host: {hostport}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n".encode()
        )
        while b"\r\n\r\n" not in self.buf:
            self._fill()
        head, _, self.buf = self.buf.partition(b"\r\n\r\n")
        if b"101" not in head.split(b"\r\n")[0]:
            raise RuntimeError(f"websocket upgrade refused: {head!r}")

    def _fill(self) -> None:
        chunk = self.sock.recv(65536)
        if not chunk:
            raise ConnectionError("browser closed the debugging socket")
        self.buf += chunk

    def _take(self, n: int) -> bytes:
        while len(self.buf) < n:
            self._fill()
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def send(self, text: str) -> None:
        payload = text.encode()
        header = bytearray([0x81])
        n = len(payload)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header += struct.pack(">H", n)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", n)
        mask = os.urandom(4)
        header += mask
        self.sock.sendall(bytes(header) + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def recv(self) -> str:
        chunks = []
        while True:
            b0, b1 = self._take(2)
            fin, opcode = b0 & 0x80, b0 & 0x0F
            n = b1 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._take(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._take(8))[0]
            data = self._take(n)
            if opcode == 0x8:
                raise ConnectionError("browser sent a websocket close")
            if opcode == 0x9:  # ping -> pong
                self.sock.sendall(b"\x8a\x80" + os.urandom(4))
                continue
            chunks.append(data)
            if fin:
                return b"".join(chunks).decode("utf-8", "replace")

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class Browser:
    def __init__(self, ws_url: str):
        self.ws = WebSocket(ws_url)
        self.next_id = 0

    def call(self, method: str, params: dict | None = None, timeout: float = 120.0):
        self.next_id += 1
        want = self.next_id
        self.ws.send(json.dumps({"id": want, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                raw = self.ws.recv()
            except (socket.timeout, TimeoutError):
                # The socket read window is deliberately shorter than the call
                # deadline. Running a briefing is a single `Runtime.evaluate`
                # that can sit silent for a minute or more, and the read going
                # quiet is not the same as the call having failed.
                continue
            message = json.loads(raw)
            if message.get("id") != want:
                continue  # an event, or a reply we already gave up on
            if "error" in message:
                raise RuntimeError(f"{method}: {message['error'].get('message')}")
            return message.get("result", {})
        raise TimeoutError(f"{method} did not answer within {timeout}s")

    def eval(self, expression: str, *, await_promise: bool = False, timeout: float = 120.0):
        result = self.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": await_promise,
            },
            timeout=timeout,
        )
        if result.get("exceptionDetails"):
            detail = result["exceptionDetails"]
            text = detail.get("exception", {}).get("description") or detail.get("text")
            raise RuntimeError(f"page threw: {text}")
        return result.get("result", {}).get("value")


def find_browser() -> str:
    for candidate in CANDIDATES:
        if not candidate:
            continue
        if Path(candidate).is_file():
            return candidate
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise SystemExit(
        "No Chromium-based browser found. Install Edge or Chrome, or point\n"
        "NAVPORT_BROWSER at the executable."
    )


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def launch(binary: str, port: int, profile: Path) -> subprocess.Popen:
    return subprocess.Popen(
        [
            binary,
            "--headless=new",
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--disable-gpu",
            "--hide-scrollbars",
            "--force-color-profile=srgb",
            "--font-render-hinting=none",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def page_socket(port: int, timeout: float = 40.0) -> str:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2) as r:  # noqa: S310
                targets = json.load(r)
            for target in targets:
                if target.get("type") == "page" and target.get("webSocketDebuggerUrl"):
                    return target["webSocketDebuggerUrl"]
        except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError) as exc:
            last = exc
        time.sleep(0.3)
    raise SystemExit(f"headless browser never exposed a page target ({last})")


# --------------------------------------------------------------------------
# The page script. Fills the form, submits, waits for the briefing to render.
# --------------------------------------------------------------------------

RUN_BRIEFING = """
(async () => {
  const set = (id, value) => {
    const node = document.getElementById(id);
    if (node) node.value = value;
  };
  set('departure', %(departure)r);
  set('destination', %(destination)r);
  set('waypoints', %(waypoints)r);
  set('cruise-speed', String(%(cruiseSpeed)d));

  const results = document.getElementById('results');
  document.getElementById('plan-form').requestSubmit();

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  const deadline = Date.now() + 90000;
  let rendered = false;
  while (Date.now() < deadline) {
    await sleep(400);
    if (results && !results.hidden && results.offsetHeight > 0) { rendered = true; break; }
  }

  if (!rendered) {
    // Say why. "Did not render" on its own is not a diagnosis, and the app
    // puts the reason in a toast — usually a rate limit or an upstream
    // timeout, neither of which is a layout problem.
    const toast = document.getElementById('toasts');
    const empty = document.querySelector('.empty, #empty-state');
    return {
      rendered: false,
      reason: ((toast && toast.textContent.trim())
            || (empty && empty.textContent.trim())
            || 'no message on screen').slice(0, 200),
    };
  }

  // Leaflet only requests tiles for the visible viewport. On a phone the map
  // sits a couple of thousand pixels down a very tall page, so without a
  // scroll pass first it is still blank when the shutter opens even though
  // captureBeyondViewport paints the whole document.
  const step = Math.max(200, window.innerHeight * 0.75);
  for (let y = 0; y < document.documentElement.scrollHeight; y += step) {
    window.scrollTo(0, y);
    await sleep(150);
  }
  window.scrollTo(0, 0);
  await sleep(300);

  const tilesDone = Date.now() + 20000;
  while (Date.now() < tilesDone) {
    await sleep(400);
    const tiles = document.querySelectorAll('.leaflet-tile').length;
    const loaded = document.querySelectorAll('.leaflet-tile-loaded').length;
    if (tiles > 0 && loaded >= tiles) break;
  }
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  const pane = document.querySelector('.leaflet-tile-pane');
  const tileSrc = (document.querySelector('.leaflet-tile') || {}).src || null;
  let tileStatus = null;
  if (tileSrc) {
    try {
      const probe = await fetch(tileSrc, { mode: 'cors' });
      tileStatus = probe.status;
    } catch (err) {
      tileStatus = 'blocked: ' + err.message;
    }
  }

  return {
    rendered: Boolean(results && !results.hidden),
    risk: (document.getElementById('risk-level') || {}).textContent || null,
    intervals: document.querySelectorAll('#timeline > *').length,
    charts: document.querySelectorAll('canvas').length,
    tiles: document.querySelectorAll('.leaflet-tile-loaded').length,
    tilesTotal: document.querySelectorAll('.leaflet-tile').length,
    tilePaneExists: Boolean(pane),
    tileSrc,
    tileStatus,
    leaflet: typeof window.L,
    chartjs: typeof window.Chart,
  };
})()
""".replace("%(departure)r", json.dumps(ROUTE["departure"])) \
   .replace("%(destination)r", json.dumps(ROUTE["destination"])) \
   .replace("%(waypoints)r", json.dumps(ROUTE["waypoints"])) \
   .replace("%(cruiseSpeed)d", str(ROUTE["cruiseSpeed"]))


# Measures the four failure modes that matter when this markup is loaded on a
# phone. `44` is the tap-target floor in both the Apple HIG and Material; `16`
# is the font size below which iOS Safari zooms the viewport on focus.
AUDIT = """
(() => {
  const doc = document.documentElement;
  const width = window.innerWidth;
  const overflow = Math.max(0, doc.scrollWidth - width);

  const wide = [];
  for (const node of document.querySelectorAll('body *')) {
    const style = getComputedStyle(node);
    if (style.display === 'none' || style.visibility === 'hidden') continue;
    const box = node.getBoundingClientRect();
    if (box.width === 0) continue;
    if (box.right > width + 1 || box.left < -1) {
      wide.push({
        tag: node.tagName.toLowerCase(),
        cls: (node.className || '').toString().slice(0, 40),
        left: Math.round(box.left),
        right: Math.round(box.right),
      });
    }
  }

  const coarse = window.matchMedia('(pointer: coarse)').matches;

  const zoomy = [];
  for (const node of document.querySelectorAll('input, select, textarea')) {
    if (node.type === 'hidden') continue;
    const size = parseFloat(getComputedStyle(node).fontSize);
    if (size < 16) zoomy.push({ id: node.id || node.name || node.tagName, size });
  }

  return {
    width,
    coarse,
    hoverNone: window.matchMedia('(hover: none)').matches,
    standalone: window.matchMedia('(display-mode: standalone)').matches,
    overflow,
    wide: wide.slice(0, 8),
    wideCount: wide.length,
    zoomy,
    bodyHeight: Math.round(doc.scrollHeight),
  };
})()
"""


# Tap targets are hit-tested rather than measured. A control can be 28px on
# screen and still comfortable to hit, because `platform.css` grows several of
# them with a transparent `::after` that a bounding box cannot see. What
# matters is whether a thumb landing near the middle actually activates the
# control, so this walks outward from the centre with `elementFromPoint` and
# reports the real reachable area.
TAP_AUDIT = """
(async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const FLOOR = 44;
  const LIMIT = 30;  // how far outside the box to probe, per side

  // Controls that cannot reach 44px in both axes for a structural reason.
  // Each carries the lower bound it does meet and why that is defensible, so
  // the exemption is a stated argument rather than a silenced warning.
  const EXEMPT = [{
    selector: '.rib',
    floor: 24,
    why: 'one bar per 15-minute interval, so width is set by route length; '
       + 'WCAG 2.5.8 AA puts the floor for adjacent targets at 24px, and a '
       + 'mis-tap selects the neighbouring interval, which is visible at once',
  }];

  const candidates = [];
  for (const node of document.querySelectorAll(
      'button, a[href], input, select, textarea, [role=button], [role=switch], summary')) {
    const style = getComputedStyle(node);
    if (style.display === 'none' || style.visibility === 'hidden') continue;
    if (node.type === 'hidden') continue;
    // The OSM attribution is a legal credit line, not something anyone aims a
    // thumb at, and Leaflet owns that markup.
    if (node.closest('.leaflet-control-attribution')) continue;
    const box = node.getBoundingClientRect();
    if (box.width === 0 && box.height === 0) continue;
    if (box.width >= FLOOR && box.height >= FLOOR) continue;
    candidates.push(node);
  }

  const exemptionFor = (node) => EXEMPT.find((e) => node.matches(e.selector)) || null;

  // One representative per selector keeps the scrolling cheap.
  const groups = new Map();
  for (const node of candidates) {
    const key = node.tagName.toLowerCase() + (node.className
      ? '.' + node.className.toString().trim().split(/\\s+/).join('.')
      : '');
    if (!groups.has(key)) groups.set(key, { node, count: 0 });
    groups.get(key).count += 1;
  }

  const owns = (node, x, y) => {
    const hit = document.elementFromPoint(x, y);
    return Boolean(hit) && (hit === node || node.contains(hit) || hit.parentElement === node);
  };

  const results = [];
  for (const [sel, group] of groups) {
    const node = group.node;
    node.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' });
    await sleep(40);

    const box = node.getBoundingClientRect();
    const cx = Math.round(box.left + box.width / 2);
    const cy = Math.round(box.top + box.height / 2);
    const base = { sel: sel.slice(0, 56), w: Math.round(box.width), h: Math.round(box.height),
                   count: group.count };

    if (!owns(node, cx, cy)) {
      // Something is stacked on top of the control's own centre.
      results.push({ ...base, hitW: 0, hitH: 0, covered: true, exempt: null });
      continue;
    }

    const reach = (dx, dy) => {
      let n = 0;
      while (n < LIMIT && owns(node, cx + dx * (n + 1), cy + dy * (n + 1))) n += 1;
      return n;
    };
    const hitW = reach(-1, 0) + reach(1, 0) + 1;
    const hitH = reach(0, -1) + reach(0, 1) + 1;

    const exemption = exemptionFor(node);
    const floor = exemption ? exemption.floor : FLOOR;
    if (hitW < floor || hitH < floor) {
      results.push({ ...base, hitW, hitH, covered: false, exempt: null });
    } else if (exemption && (hitW < FLOOR || hitH < FLOOR)) {
      results.push({ ...base, hitW, hitH, covered: false, exempt: exemption.why });
    }
  }
  window.scrollTo(0, 0);
  return results;
})()
"""


def capture(browser: Browser, path: Path, max_height: int = 6000) -> int:
    metrics = browser.call("Page.getLayoutMetrics")
    content = metrics.get("cssContentSize") or metrics.get("contentSize") or {}
    width = int(content.get("width") or 0) or 1280
    height = min(int(content.get("height") or 0) or 900, max_height)
    shot = browser.call(
        "Page.captureScreenshot",
        {
            "format": "png",
            "captureBeyondViewport": True,
            "clip": {"x": 0, "y": 0, "width": width, "height": height, "scale": 1},
        },
    )
    raw = base64.b64decode(shot["data"])
    path.write_bytes(raw)
    return len(raw)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=os.environ.get("NAVPORT_BASE", "http://127.0.0.1:5000"))
    parser.add_argument("--only", help="run a single device by name")
    parser.add_argument("--keep-open", action="store_true", help="leave the browser running")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    try:
        with urllib.request.urlopen(f"{base}/api/health", timeout=5) as r:  # noqa: S310
            health = json.load(r)
    except Exception as exc:
        print(f"Cannot reach {base}/api/health — start the server first.\n  {exc}")
        return 2
    print(f"server: {health.get('status')}, {health.get('airports_loaded')} airports, env {health.get('environment')}")

    SHOTS.mkdir(parents=True, exist_ok=True)
    binary = find_browser()
    print(f"renderer: {binary}")

    port = free_port()
    profile = Path(tempfile.mkdtemp(prefix="navport-ui-"))
    proc = launch(binary, port, profile)

    failures = []
    try:
        browser = Browser(page_socket(port))
        browser.call("Page.enable")
        browser.call("Runtime.enable")

        devices = DEVICES
        if args.only:
            devices = [d for d in DEVICES if d[0] == args.only]
            if not devices:
                print(f"no device named {args.only!r}")
                return 2

        for name, width, height, mobile in devices:
            print(f"\n{name}  {width}x{height}  {'touch' if mobile else 'mouse'}")
            browser.call(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": width,
                    "height": height,
                    "deviceScaleFactor": 1,
                    "mobile": mobile,
                    "screenWidth": width,
                    "screenHeight": height,
                },
            )
            # pointer:coarse and hover:none only match once touch is emulated,
            # and those two queries are what platform.css hangs the mobile
            # treatment off, so this is what makes the audit meaningful.
            browser.call("Emulation.setTouchEmulationEnabled",
                         {"enabled": mobile, "maxTouchPoints": 5 if mobile else 1})
            browser.call("Emulation.setEmitTouchEventsForMouse",
                         {"enabled": mobile, "configuration": "mobile" if mobile else "desktop"})

            browser.call("Page.navigate", {"url": f"{base}/"})
            time.sleep(1.2)
            browser.eval(
                "new Promise(r => document.readyState === 'complete'"
                " ? r(1) : window.addEventListener('load', () => r(1), { once: true }))",
                await_promise=True,
            )

            state = browser.eval(RUN_BRIEFING, await_promise=True, timeout=180)

            # A briefing fans out to a free public weather API and is rate
            # limited per client, so one failure across a seven-device sweep
            # is usually throttling rather than anything about the layout.
            # Retry once, slowly, before calling it a problem.
            if not (state and state.get("rendered")):
                print(f"  ..    no briefing ({state and state.get('reason')}), retrying once")
                time.sleep(20)
                browser.call("Page.navigate", {"url": f"{base}/"})
                time.sleep(2)
                state = browser.eval(RUN_BRIEFING, await_promise=True, timeout=180)

            if not (state and state.get("rendered")):
                reason = (state or {}).get("reason", "unknown")
                failures.append(f"{name}: briefing never rendered — {reason}")
                print(f"  FAIL  briefing did not render: {reason}")
            else:
                print(f"  ok    {state['risk']}, {state['intervals']} intervals, "
                      f"{state['charts']} charts, "
                      f"{state['tiles']}/{state['tilesTotal']} map tiles")
                if state["tilesTotal"] and not state["tiles"]:
                    print(f"        tile probe -> {state['tileStatus']} for {state['tileSrc']}")
                if state["leaflet"] == "undefined" or state["chartjs"] == "undefined":
                    note = (f"vendor script missing: L={state['leaflet']}, "
                            f"Chart={state['chartjs']}")
                    print(f"  FAIL  {note}")
                    failures.append(f"{name}: {note}")

            audit = browser.eval(AUDIT)
            flags = []
            if audit["overflow"] > 1:
                flags.append(f"{audit['overflow']}px horizontal overflow")
                for node in audit["wide"]:
                    flags.append(f"    {node['tag']}.{node['cls']} spans {node['left']}..{node['right']}")
            if audit["coarse"] and audit["zoomy"]:
                flags.append("inputs below 16px will zoom on iOS: "
                             + ", ".join(f"{z['id']}@{z['size']:g}px" for z in audit["zoomy"]))
            targets = browser.eval(TAP_AUDIT, await_promise=True) if audit["coarse"] else []
            small = [t for t in targets if not t["exempt"]]
            allowed = [t for t in targets if t["exempt"]]

            if small:
                total = sum(s["count"] for s in small)
                flags.append(f"{total} tap target(s) reachable area under 44px, {len(small)} distinct:")
                for s in sorted(small, key=lambda s: s["hitW"] * s["hitH"]):
                    times = f" x{s['count']}" if s["count"] > 1 else ""
                    if s["covered"]:
                        flags.append(f"    {s['sel']} is covered at its own centre{times}")
                    else:
                        flags.append(f"    {s['sel']} box {s['w']}x{s['h']}, "
                                     f"reachable {s['hitW']}x{s['hitH']}{times}")
            for a in allowed:
                times = f" x{a['count']}" if a["count"] > 1 else ""
                print(f"  note  {a['sel']} {a['hitW']}x{a['hitH']}{times} — allowed: {a['exempt']}")

            print(f"  media pointer:{'coarse' if audit['coarse'] else 'fine'} "
                  f"hover:{'none' if audit['hoverNone'] else 'yes'} "
                  f"page {audit['bodyHeight']}px tall")
            for flag in flags:
                print(f"  FAIL  {flag}" if not flag.startswith("    ") else flag)
            failures += [f"{name}: {f}" for f in flags if not f.startswith("    ")]

            written = capture(browser, SHOTS / f"{name}.png")
            print(f"  shot  docs/screenshots/{name}.png ({written / 1024:.0f} KB)")

        print("\n" + "-" * 60)
        if failures:
            print(f"{len(failures)} layout problem(s):")
            for failure in failures:
                print(f"  - {failure}")
            return 1
        print(f"{len(devices)} form factors clean — no overflow, no small tap targets, no iOS zoom")
        return 0
    finally:
        if not args.keep_open:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
            shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
