import json
import os
import sys
from pathlib import Path

TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(TOOL_DIR, 'config.json')

DEFAULT_PORTS = {
    'auth': 9099,
    'firestore': 8080,
    'storage': 9199,
    'ui': 4000,
}


def _find_upwards(filename, start_dir):
    d = os.path.abspath(start_dir)
    while True:
        if os.path.isfile(os.path.join(d, filename)):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def _detect_android_sdk(project_root):
    for var in ('ANDROID_HOME', 'ANDROID_SDK_ROOT'):
        val = os.environ.get(var)
        if val and os.path.isdir(val):
            return os.path.normpath(val)
    local_props = os.path.join(project_root, 'android', 'local.properties')
    if os.path.isfile(local_props):
        with open(local_props) as f:
            for line in f:
                line = line.strip()
                if line.startswith('sdk.dir'):
                    parts = line.split('=', 1)
                    if len(parts) == 2:
                        sdk = os.path.normpath(parts[1].strip())
                        if os.path.isdir(sdk):
                            return sdk
    if sys.platform == 'win32':
        local_appdata = os.environ.get('LOCALAPPDATA', '')
        candidate = os.path.join(local_appdata, 'Android', 'Sdk')
        if os.path.isdir(candidate):
            return candidate
    elif sys.platform == 'darwin':
        candidate = os.path.join(str(Path.home()), 'Library', 'Android', 'sdk')
        if os.path.isdir(candidate):
            return candidate
    else:
        xdg = os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local' / 'share'))
        candidate = os.path.join(xdg, 'android', 'sdk')
        if os.path.isdir(candidate):
            return candidate
        candidate = os.path.join(str(Path.home()), 'Android', 'Sdk')
        if os.path.isdir(candidate):
            return candidate
    return ''


def _detect_java_home():
    env = os.environ.get('JAVA_HOME')
    if env and os.path.isdir(env):
        java_bin = os.path.join(env, 'bin', 'java.exe' if sys.platform == 'win32' else 'java')
        if os.path.isfile(java_bin):
            return os.path.normpath(env)
    candidates = []
    if sys.platform == 'win32':
        candidates = [
            r'C:\Program Files\Eclipse Adoptium\jdk-21.0.11.10-hotspot',
            r'C:\Program Files\Eclipse Adoptium\jdk-21.0.12.8-hotspot',
            r'C:\Program Files\Java\jdk-21',
            r'C:\Program Files\Java\jdk-17',
        ]
    else:
        import glob
        for pattern in ('/usr/lib/jvm/*', '/usr/lib/jvm/java-*-openjdk*',
                        '/Library/Java/JavaVirtualMachines/*/Contents/Home'):
            for c in glob.glob(pattern):
                if os.path.isdir(c):
                    java_bin = os.path.join(c, 'bin', 'java')
                    if os.path.isfile(java_bin):
                        candidates.append(c)
    for c in candidates:
        java_bin = os.path.join(c, 'bin', 'java.exe' if sys.platform == 'win32' else 'java')
        if os.path.isfile(java_bin):
            return c
    return ''


def _detect_flutter_sdk():
    env = os.environ.get('FLUTTER_ROOT')
    if env:
        return env
    flutter_exe = 'flutter.bat' if sys.platform == 'win32' else 'flutter'
    which = os.environ.get('PATH', '').split(os.pathsep)
    for p in which:
        candidate = os.path.normpath(os.path.join(p, '..'))
        flutter_path = os.path.join(candidate, 'bin', flutter_exe)
        if os.path.isfile(flutter_path):
            return candidate
    home = str(Path.home())
    candidates = [os.path.join(home, 'flutter')]
    if sys.platform == 'win32':
        local_appdata = os.environ.get('LOCALAPPDATA', '')
        candidates.append(os.path.join(local_appdata, 'flutter'))
        candidates.append(r'C:\tools\flutter')
    else:
        candidates.append('/opt/flutter')
        candidates.append('/usr/local/flutter')
    for c in candidates:
        if os.path.isfile(os.path.join(c, 'bin', flutter_exe)):
            return c
    return ''


def _find_emulator_exe(android_sdk):
    if not android_sdk:
        return None
    exe_name = 'emulator.exe' if sys.platform == 'win32' else 'emulator'
    path = os.path.join(android_sdk, 'emulator', exe_name)
    return path if os.path.isfile(path) else None


def _find_adb_exe(android_sdk):
    if not android_sdk:
        return None
    exe_name = 'adb.exe' if sys.platform == 'win32' else 'adb'
    path = os.path.join(android_sdk, 'platform-tools', exe_name)
    return path if os.path.isfile(path) else None


class Config:
    def __init__(self):
        self.project_root = ''
        self.java_home = ''
        self.android_sdk = ''
        self.flutter_sdk = ''
        self.flutter_device = ''
        self.use_emulators = True
        self.emulator_ports = dict(DEFAULT_PORTS)
        self.current_profile = 'default'
        self.profiles = {}
        self.session_open_modals = []

    def _as_dict(self):
        return {
            'project_root': self.project_root,
            'java_home': self.java_home,
            'android_sdk': self.android_sdk,
            'flutter_sdk': self.flutter_sdk,
            'flutter_device': self.flutter_device,
            'use_emulators': self.use_emulators,
            'emulator_ports': dict(self.emulator_ports),
        }

    def _from_dict(self, data):
        self.project_root = data.get('project_root', '')
        self.java_home = data.get('java_home', '')
        self.android_sdk = data.get('android_sdk', '')
        self.flutter_sdk = data.get('flutter_sdk', '')
        self.flutter_device = data.get('flutter_device', '')
        self.use_emulators = data.get('use_emulators', True)
        ports = data.get('emulator_ports', {})
        for k in DEFAULT_PORTS:
            self.emulator_ports[k] = ports.get(k, DEFAULT_PORTS[k])

    def load(self):
        if not os.path.isfile(CONFIG_FILE):
            return False
        try:
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
            self._from_dict(data)
            self.current_profile = data.get('current_profile', 'default')
            self.profiles = data.get('profiles', {})
            self.session_open_modals = data.get('session_open_modals', [])
            return True
        except Exception:
            return False

    def save(self):
        profile_data = self._as_dict()
        if self.current_profile not in self.profiles:
            self.profiles[self.current_profile] = profile_data
        else:
            self.profiles[self.current_profile] = profile_data
        data = profile_data.copy()
        data['current_profile'] = self.current_profile
        data['profiles'] = self.profiles
        data['session_open_modals'] = self.session_open_modals
        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f, indent=2)

    def list_profiles(self):
        return sorted(self.profiles.keys())

    def save_profile(self, name):
        self.profiles[name] = self._as_dict()
        self.current_profile = name
        self.save()

    def load_profile(self, name):
        if name not in self.profiles:
            return False
        self._from_dict(self.profiles[name])
        self.current_profile = name
        return True

    def delete_profile(self, name):
        if name in self.profiles:
            del self.profiles[name]
            if self.current_profile == name:
                self.current_profile = 'default'
            self.save()
            return True
        return False

    def auto_detect(self, project_root_hint=''):
        if project_root_hint and os.path.isdir(project_root_hint):
            self.project_root = project_root_hint
        else:
            found = _find_upwards('pubspec.yaml', TOOL_DIR)
            if found:
                self.project_root = found

        if self.project_root:
            self.android_sdk = _detect_android_sdk(self.project_root)

        self.java_home = _detect_java_home()
        self.flutter_sdk = _detect_flutter_sdk()

    @property
    def emulator_exe(self):
        return _find_emulator_exe(self.android_sdk)

    @property
    def adb_exe(self):
        return _find_adb_exe(self.android_sdk)

    @property
    def is_valid(self):
        return bool(self.project_root) and os.path.isdir(self.project_root)
