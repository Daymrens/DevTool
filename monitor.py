import socket
import threading
import time


def check_port(host, port, timeout=1.0):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


class ServiceMonitor:
    def __init__(self, status_callback, config=None):
        self.status_callback = status_callback
        self.config = config
        self._running = False
        self._thread = None
        self.statuses = {}
        self._build_services()

    def _build_services(self):
        if self.config and self.config.use_emulators:
            ports = self.config.emulator_ports
            self.services = {
                'Auth':       {'port': ports.get('auth', 9099), 'label': f'Auth:{ports.get("auth", 9099)}'},
                'Firestore':  {'port': ports.get('firestore', 8080), 'label': f'Firestore:{ports.get("firestore", 8080)}'},
                'Storage':    {'port': ports.get('storage', 9199), 'label': f'Storage:{ports.get("storage", 9199)}'},
                'Emulator UI':{'port': ports.get('ui', 4000), 'label': f'Emulator UI:{ports.get("ui", 4000)}'},
            }
        else:
            self.services = {}
        self.statuses = {name: False for name in self.services}

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _run(self):
        while self._running:
            changed = False
            for name, info in self.services.items():
                alive = check_port('127.0.0.1', info['port'])
                if self.statuses.get(name) != alive:
                    self.statuses[name] = alive
                    changed = True
            if changed:
                self.status_callback(dict(self.statuses))
            time.sleep(2)
