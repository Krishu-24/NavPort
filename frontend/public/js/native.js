/**
 * Marks the document when NavPort is running inside a native app shell.
 *
 * Loaded synchronously from <head>, before the stylesheets have painted, so
 * `platform.css` can style the title bar on the first frame. A classic script
 * rather than a module because modules are deferred by definition and would
 * apply the class after the page is already on screen.
 *
 * The detection is duplicated in js/config.js as `IS_NATIVE_SHELL`, which is
 * what the rest of the app imports. Keep the two in step.
 */
(function () {
    'use strict';

    var isNative = Boolean(
        window.__TAURI__
        || window.__TAURI_INTERNALS__
        || window.Capacitor
        || window.location.protocol === 'tauri:'
        || window.location.protocol === 'capacitor:'
    );

    if (isNative) {
        document.documentElement.classList.add('is-native');
    }
})();
