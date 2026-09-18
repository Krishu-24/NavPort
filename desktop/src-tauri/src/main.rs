// Prevents a console window from opening alongside the app on Windows release
// builds. Left on in debug so `println!` and panics stay visible.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    navport_lib::run()
}
