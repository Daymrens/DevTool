import os
import re
import subprocess
import sys
import threading
import webbrowser

_ANSI_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

if sys.platform == 'win32':
    _CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW
else:
    _CREATE_NO_WINDOW = 0


def _strip_ansi(text):
    return _ANSI_RE.sub('', text)


def _stream_output(proc, log_cb, tag):
    try:
        for line in iter(proc.stdout.readline, ''):
            if line:
                clean = _strip_ansi(line.rstrip())
                if clean:
                    log_cb(clean, tag)
            else:
                break
    except Exception as e:
        log_cb(f'Output stream error: {e}', 'ERROR')


class ProcessController:
    def __init__(self, config, log_callback, gui_after):
        self.config = config
        self.log = log_callback
        self.after = gui_after
        self._procs = {}
        self._lock = threading.Lock()
        self._term_cbs = {}

    def set_terminal_callback(self, tab, callback):
        self._term_cbs[tab] = callback

    def _term_write(self, tab, text):
        cb = self._term_cbs.get(tab)
        if cb:
            cb(text)

    def _set_proc(self, key, proc):
        with self._lock:
            self._procs[key] = proc

    def _pop_proc(self, key):
        with self._lock:
            return self._procs.pop(key, None)

    def _get_proc(self, key):
        with self._lock:
            return self._procs.get(key)

    def kill_all(self):
        with self._lock:
            keys = list(self._procs.keys())
        for key in keys:
            self._kill_proc_tree(key)

    def _kill_proc_tree(self, key):
        with self._lock:
            proc = self._procs.pop(key, None)
        if proc is None:
            return
        try:
            import psutil
            parent = psutil.Process(proc.pid)
            for child in parent.children(recursive=True):
                try:
                    child.kill()
                except Exception:
                    pass
            parent.kill()
        except ImportError:
            proc.kill()
        except Exception:
            proc.kill()

    def _on_done(self, key, callback):
        self._pop_proc(key)
        if callback:
            self.after(0, callback)

    def is_busy(self, key=None):
        with self._lock:
            if key:
                return key in self._procs
            return bool(self._procs)

    def abort_all(self):
        self.log('Aborting all processes...', 'WARNING')
        self.kill_all()

    # --- helpers ---

    def _env_with_java(self):
        env = os.environ.copy()
        jh = self.config.java_home
        if jh:
            env['JAVA_HOME'] = jh
            env['PATH'] = os.path.join(jh, 'bin') + os.pathsep + env.get('PATH', '')
        npm = os.path.join(os.environ.get('APPDATA', ''), 'npm')
        if os.path.isdir(npm) and npm not in env['PATH']:
            env['PATH'] = npm + os.pathsep + env['PATH']
        return env

    def _popen_cmd(self, args, **kwargs):
        try:
            return subprocess.Popen(args, **kwargs)
        except FileNotFoundError:
            self.log(f'Executable not found: {args[0]}', 'ERROR')
            return None

    def _popen_shell(self, cmd, **kwargs):
        try:
            return subprocess.Popen(cmd, shell=True, **kwargs)
        except Exception as e:
            self.log(f'Command failed: {cmd[:120]} — {e}', 'ERROR')
            return None

    # --- Firebase Emulators ---

    def start_emulators(self, on_start=None, on_done=None):
        def _run():
            proc = None
            if sys.platform == 'win32':
                script = os.path.join(self.config.project_root, 'emulators_start.ps1')
                if os.path.isfile(script):
                    self.log('Starting via emulators_start.ps1', 'INFO')
                    proc = self._popen_cmd(
                        ['powershell.exe', '-ExecutionPolicy', 'Bypass', '-NoLogo',
                         '-File', script],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, cwd=self.config.project_root,
                        creationflags=_CREATE_NO_WINDOW, bufsize=1,
                    )
            else:
                sh_script = os.path.join(self.config.project_root, 'emulators_start.sh')
                if os.path.isfile(sh_script):
                    self.log('Starting via emulators_start.sh', 'INFO')
                    proc = self._popen_cmd(
                        ['sh', sh_script],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, cwd=self.config.project_root,
                        creationflags=_CREATE_NO_WINDOW, bufsize=1,
                    )
            if proc is None:
                env = self._env_with_java()
                proc = self._popen_shell(
                    'firebase emulators:start --only auth,firestore,storage',
                    env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, cwd=self.config.project_root,
                    creationflags=_CREATE_NO_WINDOW, bufsize=1,
                )

            if proc is None:
                return

            self._set_proc('emulators', proc)
            if on_start:
                self.after(0, on_start)
            self._term_write('firebase', '> Starting Firebase Emulators...\n')
            try:
                for line in iter(proc.stdout.readline, ''):
                    if line:
                        clean = _strip_ansi(line.rstrip())
                        if clean:
                            self.log(clean, 'EMULATOR')
                            self._term_write('firebase', clean + '\n')
                    else:
                        break
            except Exception:
                pass
            proc.wait()
            self._on_done('emulators', on_done)

        threading.Thread(target=_run, daemon=True).start()

    def stop_emulators(self, on_done=None):
        def _run():
            self._kill_proc_tree('emulators')

            stopped_script = False
            if sys.platform == 'win32':
                script = os.path.join(self.config.project_root, 'emulators_stop.ps1')
                if os.path.isfile(script):
                    subprocess.run(
                        ['powershell.exe', '-ExecutionPolicy', 'Bypass', '-NoLogo',
                         '-File', script],
                        capture_output=True, timeout=10,
                        creationflags=_CREATE_NO_WINDOW,
                    )
                    stopped_script = True
            else:
                sh_script = os.path.join(self.config.project_root, 'emulators_stop.sh')
                if os.path.isfile(sh_script):
                    subprocess.run(
                        ['sh', sh_script],
                        capture_output=True, timeout=10,
                    )
                    stopped_script = True
            if not stopped_script:
                try:
                    import psutil
                    terms = ['firestore', 'firebase', 'emulator', 'cloud-firestore']
                    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
                        try:
                            if p.info['name'] and 'java' in p.info['name'].lower():
                                cmd = ' '.join(p.info['cmdline'] or []).lower()
                                if any(t in cmd for t in terms):
                                    p.kill()
                        except Exception:
                            pass
                except ImportError:
                    pass

            self.log('Emulators stopped.', 'SUCCESS')
            if on_done:
                self.after(0, on_done)

        threading.Thread(target=_run, daemon=True).start()

    # --- Flutter ---

    def flutter_run(self, on_start=None, on_done=None):
        def _run():
            device = self.config.flutter_device
            cmd = 'flutter run'
            if device:
                cmd += f' -d {device}'

            proc = self._popen_shell(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=self.config.project_root,
                creationflags=_CREATE_NO_WINDOW, bufsize=1,
            )
            if proc is None:
                return

            self._set_proc('flutter', proc)
            if on_start:
                self.after(0, on_start)
            self._term_write('flutter', f'> {cmd}\n')
            try:
                for line in iter(proc.stdout.readline, ''):
                    if line:
                        clean = _strip_ansi(line.rstrip())
                        if clean:
                            self.log(clean, 'FLUTTER')
                            self._term_write('flutter', clean + '\n')
                    else:
                        break
            except Exception:
                pass
            proc.wait()
            self._on_done('flutter', on_done)

        threading.Thread(target=_run, daemon=True).start()

    def flutter_hot_reload(self):
        with self._lock:
            proc = self._procs.get('flutter')
        if proc and proc.stdin:
            try:
                proc.stdin.write('r\n')
                proc.stdin.flush()
                self.log('Hot reload triggered.', 'FLUTTER')
            except Exception as e:
                self.log(f'Hot reload failed: {e}', 'ERROR')
        else:
            self.log('Flutter app not running.', 'WARNING')

    def stop_flutter(self, on_done=None):
        self._kill_proc_tree('flutter')
        self.log('Flutter stopped.', 'SUCCESS')
        if on_done:
            self.after(0, on_done)

    def flutter_pub_get(self, on_done=None):
        self._one_shot('flutter pub get', 'BUILD', on_done, key='pub_get')

    def build_runner(self, on_done=None):
        self._one_shot('dart run build_runner build --delete-conflicting-outputs', 'BUILD', on_done, key='build_runner')

    def flutter_build_apk(self, on_done=None):
        self._apk_path = None
        def _run():
            proc = self._popen_shell(
                'flutter build apk',
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=self.config.project_root,
                creationflags=_CREATE_NO_WINDOW, bufsize=1,
            )
            if proc is None:
                if on_done:
                    self.after(0, on_done)
                return
            self._set_proc('build_apk', proc)
            apk_re = re.compile(r'Built\s+(.+\.apk)\s*(?:\(([\d.]+\s*\w+)\))?')
            try:
                for line in iter(proc.stdout.readline, ''):
                    if line:
                        clean = _strip_ansi(line.rstrip())
                        if clean:
                            self.log(clean, 'BUILD')
                            m = apk_re.search(clean)
                            if m:
                                p = m.group(1)
                                size = m.group(2)
                                absp = os.path.normpath(os.path.join(self.config.project_root, p))
                                self._apk_path = absp
                                if os.path.isfile(absp):
                                    sz = f' ({size})' if size else f' ({os.path.getsize(absp) / 1e6:.1f} MB)'
                                    self.log(f'APK: {absp}{sz}', 'SUCCESS')
                    else:
                        break
            except Exception:
                pass
            proc.wait()
            self._pop_proc('build_apk')
            if proc.returncode == 0 and self._apk_path and os.path.isfile(self._apk_path):
                self.log('flutter build apk completed.', 'SUCCESS')
            elif proc.returncode != 0:
                self.log(f'flutter build apk failed (code {proc.returncode}).', 'ERROR')
            if on_done:
                self.after(0, on_done)
        threading.Thread(target=_run, daemon=True).start()

    def get_apk_path(self):
        return getattr(self, '_apk_path', None)

    def flutter_analyze(self, on_done=None):
        self._one_shot('flutter analyze', 'BUILD', on_done, key='analyze')

    def flutter_clean(self, on_done=None):
        def _run():
            self._one_shot('flutter clean', 'BUILD', key='clean')
            import time
            time.sleep(1)
            self._one_shot('flutter pub get', 'BUILD', on_done, key='pub_get')
        threading.Thread(target=_run, daemon=True).start()

    def flutter_test(self, on_done=None):
        self._one_shot('flutter test', 'BUILD', on_done, key='test')

    def flutter_doctor(self, on_done=None):
        self._one_shot('flutter doctor', 'BUILD', on_done, key='doctor')

    def flutter_upgrade(self, on_done=None):
        self._one_shot('flutter upgrade', 'BUILD', on_done, key='upgrade')

    def pub_upgrade(self, on_done=None):
        self._one_shot('flutter pub upgrade', 'BUILD', on_done, key='pub_upgrade')

    def pub_outdated(self, on_done=None):
        self._one_shot('flutter pub outdated', 'BUILD', on_done, key='pub_outdated')

    def flutter_logs(self, on_start=None, on_done=None):
        def _run():
            proc = self._popen_shell(
                'flutter logs',
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=self.config.project_root,
                creationflags=_CREATE_NO_WINDOW, bufsize=1,
            )
            if proc is None:
                return
            self._set_proc('flutter_logs', proc)
            if on_start:
                self.after(0, on_start)
            self._term_write('flutter', '> flutter logs\n')
            try:
                for line in iter(proc.stdout.readline, ''):
                    if line:
                        clean = _strip_ansi(line.rstrip())
                        if clean:
                            self.log(clean, 'FLUTTER')
                            self._term_write('flutter', clean + '\n')
                    else:
                        break
            except Exception:
                pass
            proc.wait()
            self._on_done('flutter_logs', on_done)
        threading.Thread(target=_run, daemon=True).start()

    def stop_flutter_logs(self, on_done=None):
        self._kill_proc_tree('flutter_logs')
        self.log('Flutter logs stopped.', 'SUCCESS')
        if on_done:
            self.after(0, on_done)

    def dart_fix(self, on_done=None):
        self._one_shot('dart fix --apply', 'BUILD', on_done, key='dart_fix')

    def dart_format(self, on_done=None):
        self._one_shot('dart format .', 'BUILD', on_done, key='dart_format')

    def _one_shot(self, cmd, tag, on_done=None, key=None):
        if key and self.is_busy(key):
            self.log(f'{key} already running.', 'WARNING')
            return
        def _run():
            proc = self._popen_shell(
                cmd,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=self.config.project_root,
                creationflags=_CREATE_NO_WINDOW, bufsize=1,
            )
            if proc is None:
                return
            if key:
                self._set_proc(key, proc)
            _stream_output(proc, self.log, tag)
            proc.wait()
            if key:
                self._pop_proc(key)
            if proc.returncode == 0:
                self.log(f'{cmd} completed.', 'SUCCESS')
            else:
                self.log(f'{cmd} failed (code {proc.returncode}).', 'ERROR')
            if on_done:
                self.after(0, on_done)
        threading.Thread(target=_run, daemon=True).start()

    # --- Android Emulator ---

    def list_avds(self):
        exe = self.config.emulator_exe
        if not exe:
            return []
        try:
            result = subprocess.run(
                [exe, '-list-avds'],
                capture_output=True, text=True, timeout=10,
                creationflags=_CREATE_NO_WINDOW,
            )
            return [l.strip() for l in result.stdout.splitlines() if l.strip()]
        except Exception:
            return []

    def launch_avd(self, avd_name, on_start=None, on_done=None):
        def _run():
            exe = self.config.emulator_exe
            if not exe:
                self.log('Android emulator executable not found.', 'ERROR')
                return
            proc = self._popen_cmd(
                [exe, '-avd', avd_name],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True,
                creationflags=_CREATE_NO_WINDOW, bufsize=1,
            )
            if proc is None:
                return

            self._set_proc('avd', proc)
            if on_start:
                self.after(0, on_start)
            _stream_output(proc, self.log, 'ANDROID')
            proc.wait()
            self._on_done('avd', on_done)

        threading.Thread(target=_run, daemon=True).start()

    def kill_avd(self, on_done=None):
        def _run():
            self._kill_proc_tree('avd')
            adb = self.config.adb_exe
            if adb:
                try:
                    subprocess.run(
                        [adb, 'emu', 'kill'],
                        capture_output=True, timeout=5,
                        creationflags=_CREATE_NO_WINDOW,
                    )
                except Exception:
                    pass
            self.log('Android emulator stopped.', 'SUCCESS')
            if on_done:
                self.after(0, on_done)

        threading.Thread(target=_run, daemon=True).start()

    def wipe_avd(self, avd_name, on_start=None, on_done=None):
        def _run():
            self._kill_proc_tree('avd')
            exe = self.config.emulator_exe
            if not exe:
                self.log('Android emulator executable not found.', 'ERROR')
                if on_done:
                    self.after(0, on_done)
                return
            self.log(f'Wiping data and cold-booting AVD: {avd_name}', 'INFO')
            proc = self._popen_cmd(
                [exe, '-avd', avd_name, '-wipe-data', '-no-snapshot-load'],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True,
                creationflags=_CREATE_NO_WINDOW, bufsize=1,
            )
            if proc is None:
                if on_done:
                    self.after(0, on_done)
                return
            self._set_proc('avd', proc)
            if on_start:
                self.after(0, on_start)
            _stream_output(proc, self.log, 'ANDROID')
            proc.wait()
            self._on_done('avd', on_done)
        threading.Thread(target=_run, daemon=True).start()

    def adb_install(self, apk_path, on_done=None):
        def _run():
            adb = self.config.adb_exe
            if not adb:
                self.log('ADB executable not found.', 'ERROR')
                if on_done:
                    self.after(0, on_done)
                return
            if not os.path.isfile(apk_path):
                self.log(f'APK not found: {apk_path}', 'ERROR')
                if on_done:
                    self.after(0, on_done)
                return
            self.log(f'Installing {os.path.basename(apk_path)}...', 'INFO')
            proc = self._popen_cmd(
                [adb, 'install', '-r', apk_path],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, creationflags=_CREATE_NO_WINDOW, bufsize=1,
            )
            if proc is None:
                if on_done:
                    self.after(0, on_done)
                return
            _stream_output(proc, self.log, 'ANDROID')
            proc.wait()
            if proc.returncode == 0:
                self.log(f'APK installed successfully.', 'SUCCESS')
            else:
                self.log(f'APK install failed (code {proc.returncode}).', 'ERROR')
            if on_done:
                self.after(0, on_done)
        threading.Thread(target=_run, daemon=True).start()

    # --- Firebase Auth ---

    def firebase_login(self):
        def _run():
            self.log('Opening Firebase login in browser...', 'INFO')
            if sys.platform == 'win32':
                proc = self._popen_cmd(
                    ['powershell.exe', '-ExecutionPolicy', 'Bypass', '-NoLogo',
                     '-Command', 'firebase login'],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, cwd=self.config.project_root,
                    creationflags=_CREATE_NO_WINDOW, bufsize=1,
                )
            else:
                proc = self._popen_shell(
                    'firebase login',
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, cwd=self.config.project_root,
                    creationflags=_CREATE_NO_WINDOW, bufsize=1,
                )
            if proc is None:
                return
            _stream_output(proc, self.log, 'INFO')
            proc.wait()
            if proc.returncode == 0:
                self.log('Firebase login successful.', 'SUCCESS')
            else:
                self.log(f'Firebase login exited with code {proc.returncode}.', 'WARNING')

        threading.Thread(target=_run, daemon=True).start()

    def firebase_logout(self):
        def _run():
            proc = self._popen_shell(
                'firebase logout',
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=self.config.project_root,
                creationflags=_CREATE_NO_WINDOW, bufsize=1,
            )
            if proc is None:
                return
            _stream_output(proc, self.log, 'INFO')
            proc.wait()
            if proc.returncode == 0:
                self.log('Firebase logout successful.', 'SUCCESS')
            else:
                self.log(f'Firebase logout failed (code {proc.returncode}).', 'WARNING')

        threading.Thread(target=_run, daemon=True).start()

    def firebase_deploy(self, target='all', on_done=None):
        def _run():
            cmd = 'firebase deploy'
            if target and target != 'all':
                target_map = {
                    'firestore': 'firestore:rules,firestore:indexes',
                    'functions': 'functions',
                    'hosting': 'hosting',
                    'storage': 'storage:rules',
                }
                only = target_map.get(target, target)
                cmd += f' --only {only}'

            proc = self._popen_shell(
                cmd,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=self.config.project_root,
                creationflags=_CREATE_NO_WINDOW, bufsize=1,
            )
            if proc is None:
                if on_done:
                    self.after(0, on_done)
                return
            _stream_output(proc, self.log, 'BUILD')
            proc.wait()
            if proc.returncode == 0:
                self.log(f'Deploy ({target}) completed.', 'SUCCESS')
            else:
                self.log(f'Deploy ({target}) failed (code {proc.returncode}).', 'ERROR')
            if on_done:
                self.after(0, on_done)

        threading.Thread(target=_run, daemon=True).start()

    # --- Git ---

    def get_git_branch(self):
        try:
            result = subprocess.run(
                ['git', '-C', self.config.project_root,
                 'rev-parse', '--abbrev-ref', 'HEAD'],
                capture_output=True, text=True, timeout=5,
                creationflags=_CREATE_NO_WINDOW,
            )
            return result.stdout.strip() if result.returncode == 0 else ''
        except Exception:
            return ''

    def git_add_all(self, on_done=None):
        self._one_shot('git add -A', 'BUILD', on_done)

    def git_commit(self, message, on_done=None):
        def _run():
            proc = self._popen_shell(
                f'git commit -m "{message}"',
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=self.config.project_root,
                creationflags=_CREATE_NO_WINDOW, bufsize=1,
            )
            if proc is None:
                if on_done:
                    self.after(0, on_done)
                return
            _stream_output(proc, self.log, 'BUILD')
            proc.wait()
            if proc.returncode == 0:
                self.log('Commit successful.', 'SUCCESS')
            else:
                self.log(f'Commit failed (code {proc.returncode}).', 'WARNING')
            if on_done:
                self.after(0, on_done)
        threading.Thread(target=_run, daemon=True).start()

    def git_status(self, on_done=None):
        self._one_shot('git status', 'BUILD', on_done, key='git_status')

    def git_log(self, on_done=None):
        self._one_shot('git log --oneline -10', 'BUILD', on_done, key='git_log')

    def git_fetch(self, on_done=None):
        self._one_shot('git fetch --all', 'BUILD', on_done, key='git_fetch')

    def git_stash(self, on_done=None):
        self._one_shot('git stash', 'BUILD', on_done, key='git_stash')

    def git_stash_pop(self, on_done=None):
        self._one_shot('git stash pop', 'BUILD', on_done, key='git_stash_pop')

    def git_diff_stat(self, on_done=None):
        self._one_shot('git diff --stat', 'BUILD', on_done, key='git_diff_stat')

    def git_diff_cached_stat(self, on_done=None):
        self._one_shot('git diff --cached --stat', 'BUILD', on_done, key='git_diff_cached')

    def git_diff(self, on_done=None):
        self._one_shot('git diff', 'BUILD', on_done, key='git_diff')

    def git_status_short(self, on_done=None):
        self._one_shot('git status --short', 'BUILD', on_done, key='git_status_short')

    def git_branch(self, on_done=None):
        self._one_shot('git branch -a', 'BUILD', on_done, key='git_branch')

    def git_pull(self, on_done=None):
        self._one_shot('git pull', 'BUILD', on_done, key='git_pull')

    def git_push(self, on_done=None):
        self._one_shot('git push', 'BUILD', on_done, key='git_push')

    # --- Firebase Data & Notifications ---

    def firebase_export_data(self, path, on_done=None):
        def _run():
            proc = self._popen_shell(
                f'firebase emulators:export "{path}"',
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=self.config.project_root,
                creationflags=_CREATE_NO_WINDOW, bufsize=1,
            )
            if proc is None:
                if on_done:
                    self.after(0, on_done)
                return
            _stream_output(proc, self.log, 'BUILD')
            proc.wait()
            if proc.returncode == 0:
                self.log(f'Emulator data exported to {path}', 'SUCCESS')
            else:
                self.log(f'Export failed (code {proc.returncode}).', 'ERROR')
            if on_done:
                self.after(0, on_done)
        threading.Thread(target=_run, daemon=True).start()

    def firebase_import_data(self, path, on_done=None):
        def _run():
            proc = self._popen_shell(
                f'firebase emulators:start --import "{path}"',
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=self.config.project_root,
                creationflags=_CREATE_NO_WINDOW, bufsize=1,
            )
            if proc is None:
                if on_done:
                    self.after(0, on_done)
                return
            _stream_output(proc, self.log, 'EMULATOR')
            proc.wait()
            if on_done:
                self.after(0, on_done)
        threading.Thread(target=_run, daemon=True).start()

    def send_test_notification(self, token, title, body, on_done=None):
        def _run():
            proc = self._popen_shell(
                f'firebase messaging:send --token "{token}" --title "{title}" --body "{body}"',
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=self.config.project_root,
                creationflags=_CREATE_NO_WINDOW, bufsize=1,
            )
            if proc is None:
                if on_done:
                    self.after(0, on_done)
                return
            _stream_output(proc, self.log, 'BUILD')
            proc.wait()
            if proc.returncode == 0:
                self.log('Test notification sent.', 'SUCCESS')
            else:
                self.log(f'Notification failed (code {proc.returncode}).', 'WARNING')
            if on_done:
                self.after(0, on_done)
        threading.Thread(target=_run, daemon=True).start()

    def _snapshots_dir(self):
        return os.path.join(self.config.project_root, 'emulator_snapshots')

    def snapshot_list(self):
        d = self._snapshots_dir()
        if not os.path.isdir(d):
            return []
        return sorted([
            name for name in os.listdir(d)
            if os.path.isdir(os.path.join(d, name))
        ])

    def snapshot_save(self, name, on_done=None):
        def _run():
            snap_dir = os.path.join(self._snapshots_dir(), name)
            os.makedirs(snap_dir, exist_ok=True)
            proc = self._popen_shell(
                f'firebase emulators:export "{snap_dir}"',
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=self.config.project_root,
                creationflags=_CREATE_NO_WINDOW, bufsize=1,
            )
            if proc is None:
                if on_done:
                    self.after(0, on_done)
                return
            _stream_output(proc, self.log, 'BUILD')
            proc.wait()
            if proc.returncode == 0:
                self.log(f'Snapshot saved: {name}', 'SUCCESS')
            else:
                self.log(f'Snapshot save failed (code {proc.returncode}).', 'ERROR')
            if on_done:
                self.after(0, on_done)
        threading.Thread(target=_run, daemon=True).start()

    def snapshot_load(self, name, on_done=None):
        def _run():
            snap_dir = os.path.join(self._snapshots_dir(), name)
            if not os.path.isdir(snap_dir):
                self.log(f'Snapshot not found: {name}', 'ERROR')
                if on_done:
                    self.after(0, on_done)
                return
            self._kill_proc_tree('emulators')
            proc = self._popen_shell(
                f'firebase emulators:start --import "{snap_dir}"',
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=self.config.project_root,
                creationflags=_CREATE_NO_WINDOW, bufsize=1,
            )
            if proc is None:
                if on_done:
                    self.after(0, on_done)
                return
            self._set_proc('emulators', proc)
            _stream_output(proc, self.log, 'EMULATOR')
            proc.wait()
            self._on_done('emulators', on_done)
        threading.Thread(target=_run, daemon=True).start()

    def snapshot_delete(self, name, on_done=None):
        def _run():
            snap_dir = os.path.join(self._snapshots_dir(), name)
            if os.path.isdir(snap_dir):
                import shutil
                shutil.rmtree(snap_dir, ignore_errors=True)
                self.log(f'Snapshot deleted: {name}', 'SUCCESS')
            if on_done:
                self.after(0, on_done)
        threading.Thread(target=_run, daemon=True).start()

    def switch_firebase_project(self, alias, on_done=None):
        def _run():
            proc = self._popen_shell(
                f'firebase use {alias}',
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=self.config.project_root,
                creationflags=_CREATE_NO_WINDOW, bufsize=1,
            )
            if proc is None:
                if on_done:
                    self.after(0, on_done)
                return
            _stream_output(proc, self.log, 'BUILD')
            proc.wait()
            if proc.returncode == 0:
                self.log(f'Switched Firebase project to: {alias}', 'SUCCESS')
            else:
                self.log(f'Switch failed (code {proc.returncode}).', 'WARNING')
            if on_done:
                self.after(0, on_done)
        threading.Thread(target=_run, daemon=True).start()

    # --- npm ---

    def npm_install(self, on_done=None):
        self._one_shot('npm install', 'BUILD', on_done, key='npm_install')

    def npm_run(self, script, on_done=None):
        self._one_shot(f'npm run {script}', 'BUILD', on_done, key='npm_run')

    def npm_test(self, on_done=None):
        self._one_shot('npm test', 'BUILD', on_done, key='npm_test')

    def npm_audit(self, on_done=None):
        self._one_shot('npm audit', 'BUILD', on_done, key='npm_audit')

    def npm_outdated(self, on_done=None):
        self._one_shot('npm outdated', 'BUILD', on_done, key='npm_outdated')

    # --- Utilities ---

    def get_flutter_version(self):
        try:
            result = subprocess.run(
                ['flutter', '--version'],
                capture_output=True, text=True, timeout=10,
                creationflags=_CREATE_NO_WINDOW,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if 'Flutter' in line and '•' not in line:
                        return line.strip()
                return result.stdout.splitlines()[0].strip() if result.stdout else ''
            return ''
        except Exception:
            return ''

    def open_emulator_ui(self):
        if self.config.use_emulators:
            port = self.config.emulator_ports.get('ui', 4000)
            webbrowser.open(f'http://localhost:{port}')
            self.log(f'Opened Emulator UI (port {port}) in browser.', 'INFO')
        else:
            webbrowser.open('https://console.firebase.google.com')
            self.log('Opened Firebase Console in browser.', 'INFO')

    def open_firestore_console(self):
        if self.config.use_emulators:
            port = self.config.emulator_ports.get('ui', 4000)
            webbrowser.open(f'http://localhost:{port}/firestore')
            self.log('Opened Firestore console in browser.', 'INFO')
        else:
            webbrowser.open('https://console.firebase.google.com')
            self.log('Opened Firebase Console in browser.', 'INFO')

    def open_project_folder(self):
        path = self.config.project_root
        try:
            if sys.platform == 'win32':
                os.startfile(path)
            elif sys.platform == 'darwin':
                subprocess.run(['open', path], check=False,
                               creationflags=_CREATE_NO_WINDOW)
            else:
                subprocess.run(['xdg-open', path], check=False,
                               creationflags=_CREATE_NO_WINDOW)
        except Exception as e:
            self.log(f'Failed to open folder: {e}', 'ERROR')
        self.log(f'Opened project folder: {path}', 'INFO')
