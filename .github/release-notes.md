Desktop apps for NavPort: the same dashboard as the website, in its own window, talking to the same API.

| Your computer | Download |
|---|---|
| Windows 10 / 11 | `NavPort_x64-setup.exe` (or `NavPort_x64.msi`) |
| Mac with an Apple chip (M1 and later) | `NavPort_aarch64.dmg` |
| Mac with an Intel chip | `NavPort_x64.dmg` |
| Linux, any distribution | `NavPort_amd64.AppImage` |
| Debian / Ubuntu | `NavPort_amd64.deb` |
| Fedora / openSUSE | `NavPort_x86_64.rpm` |

These builds aren't code-signed (a signing certificate costs money), so the first launch shows a warning:

- **Windows**: "Windows protected your PC". Click **More info → Run anyway**.
- **macOS**: "cannot be opened". Right-click the app → **Open** → **Open**.
- **Linux AppImage**: make it executable first: `chmod +x NavPort_amd64.AppImage`.

`SHA256SUMS.txt` lists each file's checksum, so you can check a download arrived intact. These are built by GitHub Actions from this tag's source, in `.github/workflows/apps.yml`.
