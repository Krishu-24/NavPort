/**
 * "Download for Windows / Mac / Linux" — the desktop app, for this computer.
 *
 * The installers live on GitHub Releases, attached by .github/workflows/apps.yml
 * under names without a version (NavPort_x64-setup.exe, not
 * NavPort_2.0.1_x64-setup.exe). That is what makes
 * /releases/latest/download/<file> a link that never goes stale: GitHub
 * redirects it to that file in whichever release is newest.
 *
 * The button stays hidden where there is nothing to offer — on a phone or
 * tablet, and inside the desktop app itself. "All downloads" in the footer
 * covers every other case.
 */

import { IS_NATIVE_SHELL } from '../config.js';
import { toast } from './toast.js';

const RELEASES = 'https://github.com/Krishu-24/NavPort/releases/latest';

const BUILDS = {
    windows: {
        label: 'Download for Windows',
        file: 'NavPort_x64-setup.exe',
        hint: 'If Windows says it protected your PC, choose More info → Run anyway. The app is not code-signed.',
    },
    macArm: {
        label: 'Download for Mac',
        file: 'NavPort_aarch64.dmg',
        hint: 'If macOS says the app can\'t be opened, right-click it and choose Open. It is not code-signed. Intel Mac? See All downloads.',
    },
    macIntel: {
        label: 'Download for Mac (Intel)',
        file: 'NavPort_x64.dmg',
        hint: 'If macOS says the app can\'t be opened, right-click it and choose Open. It is not code-signed.',
    },
    linux: {
        label: 'Download for Linux',
        file: 'NavPort_amd64.AppImage',
        hint: 'Make the AppImage executable (chmod +x) and run it. Prefer a .deb or .rpm? See All downloads.',
    },
};

/** Which build suits this computer, or null when none does. */
async function detect() {
    const ua = navigator.userAgent;
    const hints = navigator.userAgentData;

    if (hints?.mobile || /Android|iPhone|iPad|iPod/i.test(ua)) return null;

    const platform = hints?.platform || navigator.platform || '';

    if (/Win/i.test(platform)) return 'windows';

    if (/Mac/i.test(platform)) {
        // iPadOS asks for desktop sites and reports itself as a Mac; a Mac
        // has no multi-touch screen.
        if (navigator.maxTouchPoints > 1) return null;

        // Only Chromium browsers say which chip a Mac has. Everywhere else
        // assume Apple Silicon, which every Mac since 2020 has; Intel owners
        // are pointed to All downloads.
        try {
            const { architecture } = await hints.getHighEntropyValues(['architecture']);
            if (architecture === 'x86') return 'macIntel';
        } catch {
            // Not Chromium, or the browser declined. Fall through.
        }
        return 'macArm';
    }

    if (/Linux/i.test(platform)) return 'linux';

    return null;
}

export async function initDownload() {
    const button = document.getElementById('get-app');
    if (!button || IS_NATIVE_SHELL) return;

    const build = BUILDS[await detect()];
    if (!build) return;

    button.href = `${RELEASES}/download/${build.file}`;
    button.querySelector('span').textContent = build.label;
    button.hidden = false;

    // The download starts without leaving the page, so this is the moment to
    // warn about the one confusing step: the unsigned-app prompt.
    button.addEventListener('click', () => toast(build.hint, 'ok', 9000));
}
