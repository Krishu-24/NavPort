# NavPort native app shells

**This is optional.** The deployment is the Docker image on Azure Container
Apps — see [docs/DEPLOYMENT.md](../docs/DEPLOYMENT.md). These Tauri wrappers
only make a window around the same `frontend/` and send API calls to that
hosted URL (`NAVPORT_API_BASE`). They are not a substitute for hosting, and
weather still requires the network.

One codebase, five targets: Windows, macOS, Linux, Android and iOS. Built with
[Tauri v2](https://v2.tauri.app).

---

## Why Tauri rather than Electron or Capacitor

| | Tauri v2 | Electron | Capacitor |
|---|---|---|---|
| Desktop | Yes | Yes | Via a community plugin |
| Android / iOS | Yes | No | Yes |
| Installer size | **~6–10 MB** | ~120–180 MB | n/a (mobile only) |
| Needs a toolchain | Rust | Node | Node |

Tauri uses the webview the OS already ships — WebView2 on Windows, WKWebView
on macOS and iOS, WebKitGTK on Linux, Android System WebView — instead of
bundling a whole copy of Chromium. That is where the 20x size difference comes
from, and it is why one project can cover desktop *and* mobile.

The cost is a Rust toolchain. Capacitor would avoid that but only covers
mobile, leaving Electron or Tauri for desktop anyway.

**You may not need any of this.** NavPort is also a PWA — installable from the
browser on all five platforms with no toolchain at all. See
[Installing as a PWA](#installing-as-a-pwa-no-toolchain) below. Build the
native shells when you want a real `.exe`, `.dmg` or `.apk` to hand over, or
app-store distribution.

---

## What you can build, from where

This is the part that catches people out. **Cross-compiling to Apple platforms
is not possible** — Apple's toolchain only runs on macOS.

| Target | Buildable on Windows | On macOS | On Linux |
|---|---|---|---|
| Windows `.exe` / `.msi` | **Yes** | No | No |
| Linux `.deb` / `.AppImage` | No | No | **Yes** |
| macOS `.dmg` | No | **Yes** | No |
| Android `.apk` / `.aab` | **Yes** | Yes | Yes |
| iOS `.ipa` | No | **Yes** (Xcode) | No |

So from your Windows machine you can build **Windows and Android** yourself.

For macOS, Linux and iOS, use the GitHub Actions workflow in
`.github/workflows/apps.yml` — GitHub gives **free macOS, Windows and Linux
runners for public repositories**, which is the normal way to solve this
without buying a Mac.

> **iOS distribution needs a paid Apple Developer account** ($99/year) to run
> on a physical device or reach TestFlight. You can build and run in the
> simulator for free. There is no way around this; it is Apple policy, not a
> Tauri limitation.

---

## Prerequisites

### Everyone

1. **Rust** — <https://rustup.rs>, or on Windows:
   ```powershell
   winget install --id Rustlang.Rustup
   rustup default stable-msvc
   ```
2. **Node.js 18+** — you already have it.

Check where you stand before installing anything:

```bash
cd desktop && npm install && npm run info
```

`tauri info` prints a tick or a cross per requirement. On the machine this was
set up on it reported WebView2 and MSVC already present and Rust missing, so
Rust was the only install needed for Windows desktop builds.

### Windows desktop builds

- **Microsoft C++ Build Tools**, with the "Desktop development with C++"
  workload checked.
- **WebView2** — already present on Windows 10 1803 and later.

### Android builds

1. **Android Studio** — <https://developer.android.com/studio>
2. In its SDK Manager, install: SDK Platform, Platform-Tools, **NDK (Side by
   side)**, Build-Tools, Command-line Tools.
3. Set the environment variables (PowerShell):
   ```powershell
   [System.Environment]::SetEnvironmentVariable("JAVA_HOME", "C:\Program Files\Android\Android Studio\jbr", "User")
   [System.Environment]::SetEnvironmentVariable("ANDROID_HOME", "$env:LocalAppData\Android\Sdk", "User")
   $VERSION = Get-ChildItem -Name "$env:LocalAppData\Android\Sdk\ndk" | Select-Object -Last 1
   [System.Environment]::SetEnvironmentVariable("NDK_HOME", "$env:LocalAppData\Android\Sdk\ndk\$VERSION", "User")
   ```
   Open a new terminal afterwards.
4. Add the Rust targets:
   ```bash
   rustup target add aarch64-linux-android armv7-linux-androideabi i686-linux-android x86_64-linux-android
   ```

### macOS / iOS builds

Xcode (the full app, not just Command Line Tools), then:

```bash
rustup target add aarch64-apple-ios x86_64-apple-ios aarch64-apple-ios-sim
brew install cocoapods
```

---

## Setup

```bash
cd desktop
npm install
npm run icons       # generates every icon format from frontend/assets/icon.png
```

Verify the toolchain sees everything it needs:

```bash
npm run info
```

---

## Development

`tauri dev` points the webview at the **running Flask server**, so you get the
live backend and hot reload of the frontend:

```bash
# terminal 1 — from the repo root
run.bat

# terminal 2
cd desktop && npm run dev
```

Because the page is served from `localhost:5000` in this mode, relative
`/api/...` paths resolve normally and nothing needs configuring.

---

## Release builds

A release build **embeds `frontend/` into the binary**. The page is then served
from `tauri://localhost`, where a relative `/api/...` points at the bundle
itself and there is no server behind it. So the build has to be told where the
API lives:

```bash
# Windows (PowerShell)
$env:NAVPORT_API_BASE="https://your-app.azurecontainerapps.io"; npm run build

# macOS / Linux
NAVPORT_API_BASE=https://your-app.azurecontainerapps.io npm run build
```

That value is read by `option_env!` in `src-tauri/src/lib.rs` and baked in at
compile time, then injected as `window.NAVPORT_API_BASE` before any page
script runs. `frontend/js/config.js` picks it up as its highest-priority
source. Compile-time rather than a config file next to the executable, so a
shipped app can't be repointed at someone else's backend.

Forget to set it and the app falls back to same-origin, which in a bundle
means no API at all — the UI loads and every request fails.

### Output locations

| Target | Path |
|---|---|
| Windows | `src-tauri/target/release/bundle/msi/` and `nsis/` |
| macOS | `src-tauri/target/release/bundle/dmg/` |
| Linux | `src-tauri/target/release/bundle/deb/` and `appimage/` |
| Android APK | `src-tauri/gen/android/app/build/outputs/apk/universal/release/` |
| Android AAB | `src-tauri/gen/android/app/build/outputs/bundle/universalRelease/` |
| iOS | `src-tauri/gen/apple/build/` |

### Android

```bash
npm run android:init     # once — generates the Gradle project
npm run android:dev      # run on a connected device or emulator
npm run android:apk      # release APK
```

A release APK must be signed before a device will install it. Generate a
keystore once:

```bash
keytool -genkey -v -keystore navport.keystore -alias navport \
        -keyalg RSA -keysize 2048 -validity 10000
```

Then follow [Tauri's signing guide](https://v2.tauri.app/distribute/sign/android/).
**Never commit the keystore or its password** — `.gitignore` already excludes
both, and losing the keystore means you can never update the app under that
identity again.

### iOS

```bash
npm run ios:init
npm run ios:dev          # simulator, no Apple account needed
npm run ios:build        # device/TestFlight — needs a paid account
```

---

## Installing as a PWA (no toolchain)

Worth trying first. Deploy the container, open the URL, and:

| Platform | How |
|---|---|
| **Android** (Chrome) | "Install app" prompt, or ⋮ → *Add to Home screen* |
| **iOS / iPadOS** (Safari) | Share → *Add to Home Screen*. Safari is the only browser that can do this |
| **Windows / macOS / Linux** (Chrome, Edge) | Install icon in the address bar, or ⋮ → *Install NavPort* |

This gives a real standalone window with no browser chrome, its own icon and
its own entry in the task switcher. `frontend/manifest.webmanifest` and
`frontend/sw.js` are what make it work.

**Weather is never cached**, deliberately — see the comment at the top of
`sw.js`. A saved METAR is indistinguishable from a current one, and ceilings
and visibility can change completely in the time it would sit in a cache. Only
the app shell is cached, so the app opens offline and tells you it has no data
rather than showing you something stale.

The shell is genuinely self-contained: Leaflet, Chart.js and the fonts are
committed under `frontend/vendor/` and bundled into the native builds, so a
packaged app needs the network only for weather and basemap tiles. That was
not true when those came from a CDN — and the symptom was subtle, because
Leaflet failing to load leaves an empty grey panel rather than an error.

---

## Troubleshooting

**`tauri dev` shows a blank window.** The Flask server isn't running. Start
`run.bat` first — `devUrl` points at `http://localhost:5000`.

**Release build loads but every request fails.** `NAVPORT_API_BASE` wasn't set
at build time. See [Release builds](#release-builds).

**Requests blocked by CSP in the packaged app.** `connect-src` in
`src-tauri/tauri.conf.json` has to name your API origin. The defaults cover
`*.azurecontainerapps.io` and `*.azurewebsites.net`; add yours if it is
elsewhere.

**Android build can't find the NDK.** `NDK_HOME` is unset or points at a
version you don't have. Re-run the PowerShell snippet above in a new terminal.

**`npm run icons` fails.** Run it from `desktop/`; the source path is relative.

Check the config is well-formed before a long build:

```bash
python ../scripts/check_tauri_config.py
```
