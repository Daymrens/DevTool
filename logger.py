import os
import queue
import threading
from datetime import datetime
from tkinter import END, Text

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')

LOG_LEVELS = {
    'INFO':    {'color': '#CCCCCC', 'tag': 'info'},
    'SUCCESS': {'color': '#4CAF50', 'tag': 'success'},
    'WARNING': {'color': '#FF9800', 'tag': 'warning'},
    'ERROR':   {'color': '#F44336', 'tag': 'error'},
    'EMULATOR':{'color': '#00BCD4', 'tag': 'emulator'},
    'FLUTTER': {'color': '#FFD740', 'tag': 'flutter'},
    'ANDROID': {'color': '#81C784', 'tag': 'android'},
    'BUILD':   {'color': '#CE93D8', 'tag': 'build'},
}


class LogHandler:
    def __init__(self, text_widget: Text):
        self.text_widget = text_widget
        self.queue = queue.Queue()
        self._setup_tags()
        self._file_lock = threading.Lock()
        self._running = True
        self._poll()

    def _setup_tags(self):
        for level, cfg in LOG_LEVELS.items():
            self.text_widget.tag_config(cfg['tag'], foreground=cfg['color'])

    def _poll(self):
        try:
            while not self.queue.empty():
                msg = self.queue.get_nowait()
                self._write_to_widget(msg)
        except Exception:
            pass
        if self._running:
            try:
                self.text_widget.after(100, self._poll)
            except Exception:
                self._running = False

    def _write_to_widget(self, msg):
        timestamp, level, text = msg
        tag = LOG_LEVELS.get(level, LOG_LEVELS['INFO'])['tag']
        line = f'[{timestamp}] [{level}] {text}\n'
        self.text_widget.insert(END, line)
        self.text_widget.tag_add(tag, f'end-2l', f'end-1c')
        self.text_widget.see(END)

    def log(self, text, level='INFO'):
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.queue.put((timestamp, level, text))
        self._write_to_file(timestamp, level, text)

    def _write_to_file(self, timestamp, level, text):
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR, exist_ok=True)
        log_file = os.path.join(LOG_DIR, f'session_{datetime.now().strftime("%Y%m%d")}.log')
        with self._file_lock:
            try:
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(f'[{timestamp}] [{level}] {text}\n')
            except OSError:
                pass

    def stop(self):
        self._running = False
