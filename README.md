# DevTool

Desktop development toolkit for Flutter + Firebase projects. Built with Python and CustomTkinter.

## Features

- **Firebase** — Start/stop/restart emulators, deploy (all / firestore / functions / hosting / storage), login/logout
- **Flutter** — Run/stop/hot reload, pub get, build runner, build APK, analyze, clean, test, doctor, upgrade, pub upgrade, dart fix/format, logs
- **Android** — Launch/kill AVDs, install APK via ADB, open Emulator UI / Firestore console
- **Git** — Add & commit, pull, push, status, log, branch, fetch, stash / stash pop
- **Tools** — Settings, switch project, environment selector, test notification, export/import Firebase emulator data, npm commands
- **Embedded Terminal** — Run arbitrary shell commands with real-time output streaming, ANSI stripping, and abort
- **Command Palette** — Ctrl+P to search and run any action
- **Toast Notifications** — Brief popups on task completion
- **Process Monitor** — Port-based health checking for Firebase emulators with live status dots

## Requirements

- Python 3.10+
- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter)
- psutil
- Pillow

## Setup

```bash
pip install -r requirements.txt
python main.py
```

On first launch, configure the project paths (project root, Java home, Android SDK, Flutter SDK) or use auto-detect. Paths are saved to `config.json`.

## Project Structure

```
pet_tracker_dev_tool/
├── main.py          # GUI entry point, modals, launcher, terminal
├── controller.py    # Process spawning/killing, all command implementations
├── config.py        # JSON config management with auto-detection
├── monitor.py       # Port-based service health checker
├── logger.py        # Thread-safe log capture with tag-based coloring
├── requirements.txt
└── config.json      # Generated on first run
```

## Configuration

All paths are configurable via `config.json` (no hardcoded paths):

- `project_root` — Flutter project directory
- `java_home` — JDK installation path
- `android_sdk` — Android SDK path
- `flutter_sdk` — Flutter SDK path
- `use_emulators` — `true` for local Firebase emulators, `false` for deployed mode
- `emulator_ports` — Port mapping for auth, firestore, storage, ui
- `flutter_device` — Default run device (auto, windows, chrome, etc.)

## Keyboard Shortcuts

| Key | Action |
|---|---|
| `Ctrl+P` | Open command palette |
| `Enter` | Run command in terminal |
| `Right-click` | Copy / Select All in terminal output |
