# DevTool — Gap Analysis & Feature Roadmap

> Based on full source review of `main.py` (1556 lines), `controller.py` (691 lines), `config.py` (167 lines), `logger.py` (72 lines), `monitor.py` (56 lines).

---

## 🔴 High Priority — Daily Pain Points

### 1. Multi-Project Switching is Broken by Design
**Where:** `config.py`, `ToolsModal` → `switch_firebase_project()`

`switch_firebase_project()` exists in the controller but there is no UI to save or name multiple project configs. Switching between LendWUs, Gas Station POS, and BMIS currently requires manually editing `config.json`.

**Fix:** Build a project profile manager that saves separate `config_{alias}.json` files per project and lets you load them from a named dropdown in `ToolsModal`. On switch, reload all path values and re-run `config.is_valid`.

---

### 2. Flutter Run Has No Output Visibility
**Where:** `controller.py` → `flutter_run()`, `FlutterModal`

`flutter_run()` opens `stdin=PIPE` for hot reload support but **stdout is not streamed to the terminal**. You can hot reload but you cannot see `print()` statements, exceptions, or `debugPrint` output from Riverpod's `DebugObserver`. The app runs silently.

**Fix:** Spawn a daemon reader thread on `proc.stdout` and pipe lines into the logger queue, the same way other long-running commands work. Tag output with the `FLUTTER` level (yellow).

---

### 3. Build APK Result is Silent
**Where:** `controller.py` → `flutter_build_apk()`, `FlutterModal`

After `flutter build apk` completes, there is no indication of the output path, file size, or a quick way to open the folder. The user has to manually navigate to `build/app/outputs/flutter-apk/`.

**Fix:** On SUCCESS, resolve the APK path, log it with file size, and add a button to open the output folder directly via `open_project_folder()` pointing at the build output directory.

---

### 4. No Firestore Emulator Data Snapshots
**Where:** `controller.py` → `firebase_export_data()` / `firebase_import_data()`, `ToolsModal`

Export and Import exist but are fully manual and untargeted. There is no way to save a **named snapshot** (e.g. `seed_paluwagan_cycle2`) and restore it on demand. For LendWUs testing across loan and contribution cycles, you need repeatable, named data states.

**Fix:** Add a snapshot manager UI in `ToolsModal` — name input, Save Snapshot / Load Snapshot / Delete buttons — backed by timestamped subdirectories inside a `emulator_snapshots/` folder in the project root.

---

### 5. Git Modal is Commit-Blind
**Where:** `main.py` → `GitModal` (l.670), `controller.py` → git commands

The Git panel can add, commit, pull, and push but there is **no diff viewer**. You are committing without seeing what is staged vs unstaged. One accidental `git add .` before a partial-state commit can pollute history.

**Fix:** Run `git diff --stat` and `git status --short` and display the output in the terminal before any commit action. Optionally add a staging area toggle (add specific files via a file list).

---

## 🟡 Medium Priority — Quality of Life Gaps

### 6. No `.env` File Manager
**Where:** `ToolsModal` → env combo

There is an env combo but no way to **view or edit** the actual `.env` or `.env.local` file contents inline. Switching between emulator and production Firebase config requires opening VS Code manually.

**Fix:** Add a small inline text editor in `ToolsModal` that reads and writes the selected `.env` file. Show key-value pairs in an editable table and save on confirm.

---

### 7. AVD Management is Read-Only
**Where:** `main.py` → `AndroidModal` (l.636), `controller.py` → `launch_avd()` / `kill_avd()`

You can launch and kill AVDs but cannot **wipe data or cold boot**. When an emulator gets into a bad state (corrupted cache, bad Firestore emulator sync), the only option is to kill and relaunch — which does not reset internal AVD state.

**Fix:** Add a "Wipe & Cold Boot" button that runs `adb emu avd snapshot reset` followed by a fresh `launch_avd()`. Optionally add AVD creation via `avdmanager create avd`.

---

### 8. No Session Restore
**Where:** `main.py` → `PetTrackerDevTool.__init__()`, app close handler

Every time the tool opens, all modals are closed and must be manually re-opened. The tool does not remember which modals were open or their last screen positions.

**Fix:** On close, write open modal names and positions to `config.json`. On startup, re-open those modals at their saved positions after the main window initializes.

---

### 9. Terminal Has No Tab Support
**Where:** `main.py` → `TerminalWidget` (l.205)

There is one shared terminal for all commands. Running `flutter run` and then needing to run a Firebase command requires killing the active process. Long-running processes like the emulator or `flutter run` block everything else.

**Fix:** Replace the single `TerminalWidget` with a tabbed terminal container — at minimum 3 tabs: `Flutter`, `Firebase`, `General`. Each tab gets its own `TerminalWidget` instance with independent process tracking.

---

### 10. No Flutter Pub Outdated Check
**Where:** `FlutterModal`, `controller.py`

`npm outdated` exists under the npm section of `ToolsModal` but there is **no equivalent for Flutter pub**. You have no in-tool way to check for outdated Dart/Flutter packages in `pubspec.yaml`.

**Fix:** Add a `Pub Outdated` button to `FlutterModal` that runs `flutter pub outdated` and streams results to the terminal. Pair it with a `pubspec.yaml` quick-view panel showing current dependency versions.

---

## 🟢 Low Priority — Polish & Completeness

### 11. No Keyboard Shortcuts Beyond Ctrl+P
**Where:** `main.py` → `PetTrackerDevTool`, `CommandPalette` (l.368)

The Command Palette covers ~55 commands but requires two keystrokes to invoke anything (Ctrl+P then search). Direct shortcuts for the most common actions are missing.

**Suggested bindings:**
| Shortcut | Action |
|---|---|
| `Ctrl+R` | Flutter Hot Reload |
| `Ctrl+B` | Flutter Build APK |
| `Ctrl+Shift+E` | Start Emulators |
| `Ctrl+Shift+X` | Stop Emulators |
| `Ctrl+G` | Open Git Modal |

---

### 12. Log Panel Has No Filtering
**Where:** `main.py` → log panel, `logger.py` → 8 colored tag levels

All 8 log levels (INFO, SUCCESS, WARNING, ERROR, EMULATOR, FLUTTER, ANDROID, BUILD) are rendered together. When the emulator is running, its verbose output buries Flutter logs and build output.

**Fix:** Add a row of toggle buttons above the log panel — one per log level — that show/hide lines by tag. Persist filter state across sessions in `config.json`.

---

### 13. Status Bar SDK Info is Static
**Where:** `main.py` → `PetTrackerDevTool` status bar

Flutter, SDK, and JDK version strings are read once at startup and never refreshed. If you update Flutter or switch channels mid-session, the status bar shows stale data.

**Fix:** Add a Refresh button next to the SDK info in the status bar that re-runs `get_flutter_version()` and repopulates the labels without a full app restart.

---

### 14. No Minimize to Tray
**Where:** `main.py` → `PetTrackerDevTool`, close handler

The tool is non-resizable and anchored left, which is a clean pattern. But closing the window kills the process tracking reference — emulators and `flutter run` become orphan processes with no way to reconnect or abort them cleanly.

**Fix:** Intercept the `WM_DELETE_WINDOW` protocol to minimize to system tray (via `pystray`) instead of destroying the window. Tray menu: Show, Stop All Processes, Quit.

---

### 15. Windows-Only Architecture
**Where:** `controller.py` → `creationflags=CREATE_NO_WINDOW`, `.ps1` scripts; `config.py` → `LOCALAPPDATA` path detection

The tool cannot run on your Linux Mint laptop at all. `CREATE_NO_WINDOW` is Windows-only, the emulator start/stop scripts are `.ps1`, and SDK auto-detection uses Windows-specific paths.

**Fix:** Wrap platform-specific calls with `sys.platform` checks. Replace `.ps1` fallbacks with `.sh` equivalents on Linux/macOS. Replace `LOCALAPPDATA` paths with `XDG_DATA_HOME` / `~/.android`. `CREATE_NO_WINDOW` can be guarded with `if sys.platform == "win32"`.

---

## Summary Table

| # | Feature | Priority | Effort |
|---|---|---|---|
| 1 | Multi-project profile manager | 🔴 High | Medium |
| 2 | Flutter run stdout streaming | 🔴 High | Low |
| 3 | Build APK result + open folder | 🔴 High | Low |
| 4 | Named Firestore emulator snapshots | 🔴 High | Medium |
| 5 | Git diff viewer before commit | 🔴 High | Low |
| 6 | `.env` file inline editor | 🟡 Medium | Medium |
| 7 | AVD wipe & cold boot | 🟡 Medium | Low |
| 8 | Session restore (modals + positions) | 🟡 Medium | Low |
| 9 | Multi-tab terminal | 🟡 Medium | High |
| 10 | Flutter pub outdated check | 🟡 Medium | Low |
| 11 | Direct keyboard shortcuts | 🟢 Low | Low |
| 12 | Log level filtering | 🟢 Low | Low |
| 13 | Status bar SDK refresh button | 🟢 Low | Low |
| 14 | Minimize to system tray | 🟢 Low | Medium |
| 15 | Cross-platform (Linux/macOS) support | 🟢 Low | High |

---

*Generated from source review — `main.py` l.1–1556, `controller.py` l.1–691, `config.py`, `logger.py`, `monitor.py`*
