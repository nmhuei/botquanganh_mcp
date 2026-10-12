# BQA Desktop Studio

[![Rust](https://img.shields.io/badge/rust-2021%20edition-orange.svg)](https://www.rust-lang.org)
[![WebKitGTK](https://img.shields.io/badge/backend-WebKitGTK%204.1-blue.svg)](https://webkitgtk.org)

BQA Desktop Studio is a native desktop application for BotQuangAnh Host MCP.
It delivers a fast and responsive user interface with low system memory usage.

---

## Technical Specifications

- **Window Management:** Powered by `tao`.
- **Web Rendering:** Powered by `wry` using system WebKitGTK.
- **Asynchronous Runtime:** Powered by `tokio`.
- **System Memory:** 0 MB browser RAM bloat compared to Electron applications.

---

## Build Prerequisites

### Debian / Ubuntu / Kali

```bash
sudo apt install -y libwebkit2gtk-4.1-dev libgtk-3-dev build-essential
```

### Fedora

```bash
sudo dnf install -y webkit2gtk4.1-devel gtk3-devel
```

### Arch Linux

```bash
sudo pacman -S webkit2gtk-4.1 gtk3
```

---

## Build and Run

Compile and execute the desktop studio binary:

```bash
# Debug run
cargo run

# Optimized release build
cargo build --release
```

The resulting binary installs to `~/.local/bin/bqa-desktop` via `install.sh`.
