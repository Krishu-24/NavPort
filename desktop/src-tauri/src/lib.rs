//! NavPort native shell.
//!
//! The shell is deliberately thin: it hosts the same `frontend/` that the web
//! build serves and does not reimplement any of it. Its one real job is
//! telling that frontend where the API lives.
//!
//! In a release build the HTML, CSS and JS are embedded in the binary, so the
//! page is served from `tauri://localhost`. A relative `/api/...` there
//! resolves to the bundle itself, where no server exists. So before any page
//! script runs, an initialisation script sets `window.NAVPORT_API_BASE`, which
//! `frontend/js/config.js` reads as its highest-priority source.
//!
//! Baked in at compile time rather than read from a file at runtime, so a
//! shipped app cannot be repointed at another backend by editing something
//! next to the executable.

/// The deployed API origin, taken from `NAVPORT_API_BASE` at compile time.
///
/// Set it when building:
///
/// ```sh
/// NAVPORT_API_BASE=https://navport.azurecontainerapps.io npm run build
/// ```
///
/// Left unset, the frontend falls back to same-origin, which is what `tauri
/// dev` wants: there the webview loads from the Flask dev server and relative
/// paths already work.
const API_BASE: Option<&str> = option_env!("NAVPORT_API_BASE");

/// JavaScript to run before the page's own scripts.
fn init_script() -> String {
    match API_BASE {
        Some(base) if !base.is_empty() => {
            // Serialised through a JSON string so a URL containing a quote or
            // a backslash cannot terminate the literal and inject code.
            let literal = json_string(base);
            format!(
                "window.NAVPORT_API_BASE = {literal};\
                 window.__NAVPORT_SHELL__ = true;"
            )
        }
        _ => "window.__NAVPORT_SHELL__ = true;".to_string(),
    }
}

/// Minimal JSON string escaping — avoids a serde dependency for one value.
fn json_string(value: &str) -> String {
    let mut out = String::with_capacity(value.len() + 2);
    out.push('"');

    for c in value.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            // Escape anything non-printable, and the two characters that
            // terminate a script block early in an HTML parser.
            '<' => out.push_str("\\u003c"),
            '>' => out.push_str("\\u003e"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }

    out.push('"');
    out
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .initialization_script(&init_script())
        .run(tauri::generate_context!())
        .expect("error while running NavPort");
}

#[cfg(test)]
mod tests {
    use super::json_string;

    #[test]
    fn escapes_quotes_and_backslashes() {
        assert_eq!(json_string(r#"a"b\c"#), r#""a\"b\\c""#);
    }

    #[test]
    fn escapes_script_terminators() {
        // A URL containing `</script>` must not be able to close the block.
        assert!(!json_string("https://x/</script>").contains("</script>"));
    }

    #[test]
    fn passes_through_a_normal_origin() {
        assert_eq!(
            json_string("https://navport.azurecontainerapps.io"),
            r#""https://navport.azurecontainerapps.io""#
        );
    }
}
