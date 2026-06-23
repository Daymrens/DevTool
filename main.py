import os
import re
import subprocess
import threading
import customtkinter as ctk
import tkinter
from tkinter import Text, filedialog, messagebox

from config import Config
from logger import LogHandler
from monitor import ServiceMonitor
from controller import ProcessController

ctk.set_appearance_mode('dark')
ctk.set_default_color_theme('blue')

C = {
    'bg': '#1b1b1f',
    'card': '#25252a',
    'border': '#35353a',
    'accent': '#d97706',
    'accent_h': '#b45309',
    'text': '#e8e0d8',
    'muted': '#8a8a8e',
    'red': '#b71c1c',
    'red_h': '#9e1616',
    'orange': '#c95e2b',
    'orange_h': '#a84d22',
    'gray': '#3a3a3e',
    'gray_h': '#2e2e32',
    'log_bg': '#141418',
}


class ClaudeButton(ctk.CTkButton):
    STYLES = {
        'primary': {'fg_color': C['accent'], 'hover_color': C['accent_h']},
        'secondary': {'fg_color': C['gray'], 'hover_color': C['gray_h']},
        'danger': {'fg_color': C['red'], 'hover_color': C['red_h']},
        'warning': {'fg_color': C['orange'], 'hover_color': C['orange_h']},
    }

    def __init__(self, master, style='secondary', **kwargs):
        kwargs.setdefault('corner_radius', 6)
        kwargs.setdefault('border_width', 0)
        kwargs.setdefault('text_color', C['text'])
        kwargs.setdefault('font', ('Segoe UI', 11))
        kwargs.setdefault('height', 30)

        if style in self.STYLES:
            for k, v in self.STYLES[style].items():
                kwargs.setdefault(k, v)

        super().__init__(master, **kwargs)


class StatusDot(ctk.CTkLabel):
    def __init__(self, master, label, **kwargs):
        self._alive = False
        text = '\u25CF  ' + label
        super().__init__(master, text=text, font=('Consolas', 11), **kwargs)
        self._set_color()

    def _set_color(self):
        color = '#4CAF50' if self._alive else '#3a3a3e'
        self.configure(text_color=color)

    def set_alive(self, alive):
        if self._alive != alive:
            self._alive = alive
            self._set_color()


class NotifyDialog(ctk.CTkToplevel):
    def __init__(self, parent, callback):
        super().__init__(parent)
        self.callback = callback
        self.title('Send Test Notification')
        self.geometry('420x260')
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        ctk.CTkLabel(self, text='FCM Test Notification',
                      font=('Segoe UI', 15, 'bold')).pack(padx=16, pady=(14, 2), anchor='w')

        frame = ctk.CTkFrame(self, fg_color='transparent')
        frame.pack(fill='x', padx=16, pady=4)

        entries = {}
        for i, (label, placeholder) in enumerate([
            ('Device Token', 'FCM device registration token'),
            ('Title', 'Notification title'),
            ('Body', 'Notification body text'),
        ]):
            ctk.CTkLabel(frame, text=label, font=('Segoe UI', 12)).grid(
                row=i, column=0, padx=(0, 8), pady=4, sticky='w')
            e = ctk.CTkEntry(frame, placeholder_text=placeholder, width=280)
            e.grid(row=i, column=1, pady=4, sticky='ew')
            entries[label.lower().replace(' ', '_')] = e

        self.entries = entries
        frame.grid_columnconfigure(1, weight=1)

        btn_frame = ctk.CTkFrame(self, fg_color='transparent')
        btn_frame.pack(fill='x', padx=16, pady=(12, 14))
        ClaudeButton(btn_frame, text='Cancel', width=90,
                      command=self.destroy).pack(side='right', padx=(8, 0))
        ClaudeButton(btn_frame, text='Send', width=90, style='primary',
                      command=self._send).pack(side='right')

    def _send(self):
        token = self.entries['device_token'].get().strip()
        title = self.entries['title'].get().strip()
        body = self.entries['body'].get().strip()
        if not token:
            messagebox.showerror('Error', 'Device Token is required.', parent=self)
            return
        self.callback(token, title, body)
        self.destroy()


class SetupDialog(ctk.CTkToplevel):
    def __init__(self, parent, config):
        super().__init__(parent)
        self.config = config
        self.result = None
        self.title('Project Setup')
        self.geometry('620x450')
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text='Configure Project',
                      font=('Segoe UI', 18, 'bold')).pack(padx=16, pady=(16, 4), anchor='w')
        ctk.CTkLabel(self, text='Set the paths for your Flutter + Firebase project.',
                      font=('Segoe UI', 12), text_color=C['muted']
                      ).pack(padx=16, pady=(0, 12), anchor='w')

        self.entries = {}
        for label, key, placeholder in [
            ('Project Root *', 'project_root', 'Select project folder'),
            ('Java Home', 'java_home', 'JDK installation path'),
            ('Android SDK', 'android_sdk', 'Android SDK path'),
            ('Flutter SDK', 'flutter_sdk', 'Flutter SDK path'),
        ]:
            frame = ctk.CTkFrame(self, fg_color='transparent')
            frame.pack(fill='x', padx=16, pady=4)
            frame.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(frame, text=label, width=110, anchor='w').grid(row=0, column=0, padx=(0, 8))
            entry = ctk.CTkEntry(frame, placeholder_text=placeholder)
            entry.grid(row=0, column=1, sticky='ew')
            entry.insert(0, getattr(self.config, key, ''))
            self.entries[key] = entry
            ClaudeButton(frame, text='Browse...', width=70, height=28,
                          command=lambda k=key: self._browse(k)).grid(row=0, column=2, padx=(6, 0))

        mode_frame = ctk.CTkFrame(self, fg_color='transparent')
        mode_frame.pack(fill='x', padx=16, pady=(12, 4))
        ctk.CTkLabel(mode_frame, text='Firebase Mode:', width=110, anchor='w').pack(side='left')
        self.mode_var = ctk.StringVar(value='emulators' if self.config.use_emulators else 'deployed')
        ctk.CTkRadioButton(mode_frame, text='Local Emulators', variable=self.mode_var, value='emulators'
                            ).pack(side='left', padx=(0, 12))
        ctk.CTkRadioButton(mode_frame, text='Deployed (production)', variable=self.mode_var, value='deployed'
                            ).pack(side='left')

        btn_frame = ctk.CTkFrame(self, fg_color='transparent')
        btn_frame.pack(fill='x', padx=16, pady=(16, 12))
        ClaudeButton(btn_frame, text='Auto-Detect', width=110,
                      command=self._auto_detect).pack(side='left', padx=(0, 8))
        ClaudeButton(btn_frame, text='Cancel', width=90,
                      command=self.destroy).pack(side='right', padx=(8, 0))
        ClaudeButton(btn_frame, text='Save', width=90, style='primary',
                      command=self._save).pack(side='right')

    def _browse(self, key):
        path = filedialog.askdirectory(title=f'Select {key} path')
        if path:
            self.entries[key].delete(0, 'end')
            self.entries[key].insert(0, path)

    def _auto_detect(self):
        hint = self.entries['project_root'].get().strip()
        self.config.auto_detect(project_root_hint=hint)
        for key in ('project_root', 'java_home', 'android_sdk', 'flutter_sdk'):
            self.entries[key].delete(0, 'end')
            self.entries[key].insert(0, getattr(self.config, key, ''))

    def _save(self):
        self.config.project_root = self.entries['project_root'].get().strip()
        self.config.java_home = self.entries['java_home'].get().strip()
        self.config.android_sdk = self.entries['android_sdk'].get().strip()
        self.config.flutter_sdk = self.entries['flutter_sdk'].get().strip()
        self.config.use_emulators = self.mode_var.get() == 'emulators'
        if not self.config.project_root or not os.path.isdir(self.config.project_root):
            messagebox.showerror('Error', 'Project Root must be a valid directory.', parent=self)
            return
        self.config.save()
        self.result = self.config
        self.destroy()


class TerminalWidget(ctk.CTkFrame):
    _ANSI_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    def __init__(self, parent, project_root):
        super().__init__(parent, fg_color=C['card'], corner_radius=8)
        self.project_root = project_root
        self._proc = None
        self._lock = threading.Lock()
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self, fg_color='transparent')
        header.grid(row=0, column=0, sticky='ew', padx=6, pady=(4, 0))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text='Terminal', font=('Segoe UI', 12, 'bold'),
                      text_color=C['text']).grid(row=0, column=0, padx=2, pady=2, sticky='w')
        self._abort_btn = ClaudeButton(header, text='\u2716  Abort', width=65, style='danger',
                                        font=('Segoe UI', 10), height=26, command=self._abort_cmd)
        self._abort_btn.grid(row=0, column=1, padx=2)
        ClaudeButton(header, text='Clear', width=55, font=('Segoe UI', 10), height=26,
                      command=self._clear).grid(row=0, column=2, padx=2)

        self._output = Text(
            self, bg='#18181c', fg='#d4d4d4', insertbackground='#d4d4d4',
            font=('Consolas', 11), relief='flat', borderwidth=0, padx=8, pady=4,
            wrap='char', state='disabled',
        )
        self._output.grid(row=1, column=0, sticky='nsew', padx=4, pady=(3, 0))
        self._output.tag_config('prompt', foreground='#7ec699')
        self._output.tag_config('error', foreground='#F44336')
        self._output.tag_config('output', foreground='#d4d4d4')

        self._ctx_menu = tkinter.Menu(self, tearoff=0, bg='#25252a', fg='#e8e0d8',
                                       activebackground='#3a3a3e', activeforeground='#e8e0d8')
        self._ctx_menu.add_command(label='Copy', command=self._copy_selection,
                                    font=('Segoe UI', 11))
        self._ctx_menu.add_separator()
        self._ctx_menu.add_command(label='Select All', command=self._select_all,
                                    font=('Segoe UI', 11))
        self._output.bind('<Button-3>', self._show_ctx_menu)

        input_frame = ctk.CTkFrame(self, fg_color='transparent')
        input_frame.grid(row=2, column=0, sticky='ew', padx=4, pady=(2, 4))
        input_frame.grid_columnconfigure(0, weight=1)

        cwd = self.project_root or '.'
        self._prompt_prefix = f'{cwd}>'
        self._prompt_label = ctk.CTkLabel(input_frame, text=self._prompt_prefix,
                                           font=('Consolas', 11), text_color='#4EC9B0')
        self._prompt_label.grid(row=0, column=0, padx=(0, 4), sticky='w')
        self._prompt_label.grid_forget()

        self._entry = ctk.CTkEntry(
            input_frame, font=('Consolas', 11),
            fg_color='#18181c', text_color='#d4d4d4', border_width=0,
        )
        self._entry.grid(row=0, column=0, sticky='ew', padx=(0, 4))
        self._entry.bind('<Return>', lambda e: self._run_cmd())

        self._run_btn = ClaudeButton(input_frame, text='Run', width=50, style='primary',
                                      font=('Segoe UI', 10), command=self._run_cmd)
        self._run_btn.grid(row=0, column=1, padx=(0, 2))

        self._write_prompt()

    def _write(self, text, tag='output'):
        self._output.configure(state='normal')
        self._output.insert('end', text, tag)
        self._output.see('end')
        self._output.configure(state='disabled')

    def _write_prompt(self):
        self._write(f'\n{self._prompt_prefix} ', 'prompt')

    def _show_ctx_menu(self, e):
        self._ctx_menu.tk_popup(e.x_root, e.y_root)

    def _copy_selection(self):
        try:
            text = self._output.selection_get()
            self.clipboard_clear()
            self.clipboard_append(text)
        except tkinter.TclError:
            pass

    def _select_all(self):
        self._output.configure(state='normal')
        self._output.tag_add('sel', '1.0', 'end')
        self._output.configure(state='disabled')

    def _run_cmd(self):
        cmd = self._entry.get().strip()
        if not cmd:
            return
        self._entry.delete(0, 'end')
        if self._proc:
            self._write('A command is already running. Abort it first.\n', 'error')
            return

        self._write(f'\n> {cmd}\n', 'prompt')
        self._entry.configure(state='disabled')
        self._run_btn.configure(state='disabled')

        def _stream():
            proc = subprocess.Popen(
                cmd, shell=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=self.project_root,
                creationflags=subprocess.CREATE_NO_WINDOW, bufsize=1,
            )
            with self._lock:
                self._proc = proc
            try:
                for line in iter(proc.stdout.readline, ''):
                    if line:
                        clean = self._ANSI_RE.sub('', line.rstrip('\n\r'))
                        if clean:
                            self.after(0, lambda t=clean + '\n': self._write(t, 'output'))
                    else:
                        break
            except Exception:
                pass
            proc.wait()
            with self._lock:
                self._proc = None
            self.after(0, self._on_cmd_done)

        threading.Thread(target=_stream, daemon=True).start()

    def _on_cmd_done(self):
        self._entry.configure(state='normal')
        self._run_btn.configure(state='normal')
        self._entry.focus()
        self._write_prompt()

    def _abort_cmd(self):
        with self._lock:
            proc = self._proc
        if proc:
            self._write('Aborting...\n', 'error')
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
            with self._lock:
                self._proc = None
            self._on_cmd_done()

    def _clear(self):
        self._output.configure(state='normal')
        self._output.delete('1.0', 'end')
        self._output.configure(state='disabled')


class CommandPalette(ctk.CTkToplevel):
    def __init__(self, parent, commands):
        super().__init__(parent)
        self.commands = commands
        self.result = None
        self.geometry('400x320')
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.configure(fg_color=C['card'])
        self.bind('<Escape>', lambda e: self.destroy())

        ctk.CTkLabel(self, text='Command Palette', font=('Segoe UI', 14, 'bold'),
                      text_color=C['accent']).pack(padx=12, pady=(10, 4), anchor='w')

        self.entry = ctk.CTkEntry(self, placeholder_text='Search commands...',
                                   font=('Segoe UI', 12))
        self.entry.pack(fill='x', padx=12, pady=(0, 6))
        self.entry.bind('<KeyRelease>', self._filter)
        self.entry.bind('<Return>', self._activate)
        self.entry.bind('<Down>', lambda e: self._move(1))
        self.entry.bind('<Up>', lambda e: self._move(-1))

        frame = ctk.CTkFrame(self, fg_color='transparent')
        frame.pack(fill='both', expand=True, padx=12, pady=(0, 10))
        sb = ctk.CTkScrollbar(frame, orientation='vertical')
        self.listbox = tkinter.Listbox(
            frame, bg='#1b1b1f', fg='#e8e0d8', selectbackground='#3a3a3e',
            selectforeground='#e8e0d8', font=('Segoe UI', 11),
            relief='flat', borderwidth=0, highlightthickness=0,
            yscrollcommand=sb.set,
        )
        sb.configure(command=self.listbox.yview)
        self.listbox.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')
        self.listbox.bind('<Double-Button-1>', self._activate)
        self.listbox.bind('<Button-3>', lambda e: self._activate())

        self._all = list(commands.keys())
        self._populate(self._all)
        self.entry.focus()

    def _populate(self, items):
        self.listbox.delete(0, 'end')
        for name in items:
            self.listbox.insert('end', f'  {name}')

    def _filter(self, e=None):
        q = self.entry.get().lower()
        if not q:
            self._populate(self._all)
            return
        matched = [n for n in self._all if q in n.lower()]
        self._populate(matched)

    def _move(self, d):
        cur = self.listbox.curselection()
        if not cur and d > 0:
            self.listbox.selection_set(0)
            return
        if not cur:
            return
        idx = cur[0] + d
        if 0 <= idx < self.listbox.size():
            self.listbox.selection_clear(0, 'end')
            self.listbox.selection_set(idx)

    def _activate(self, e=None):
        cur = self.listbox.curselection()
        if not cur:
            return
        name = self.listbox.get(cur[0]).strip()
        cmd = self.commands.get(name)
        if cmd:
            self.destroy()
            cmd()


class ModalBase(ctk.CTkToplevel):
    _open_count = 0

    def __init__(self, parent, app, title, w, h):
        super().__init__(parent)
        self.app = app
        self.title(title)
        self.configure(fg_color=C['border'])
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        base_x = parent.winfo_x() + parent.winfo_width() + 10
        base_y = parent.winfo_y() + 40
        offset = ModalBase._open_count * 30
        ModalBase._open_count += 1
        mx = min(base_x + offset, sw - w - 20)
        my = min(base_y + offset, sh - h - 60)
        self.geometry(f'{w}x{h}+{mx}+{my}')
        self.resizable(False, False)
        self.transient(parent)
        self.protocol('WM_DELETE_WINDOW', self._on_close)

        inner = ctk.CTkFrame(self, fg_color=C['bg'], corner_radius=0)
        inner.pack(fill='both', expand=True, padx=1, pady=1)

        ctk.CTkLabel(inner, text='\u25C9  ' + title,
                      font=('Segoe UI', 13, 'bold'), text_color=C['accent'],
                      ).pack(padx=14, pady=(10, 0), anchor='w')

        bar = ctk.CTkFrame(inner, height=2, fg_color=C['accent'], corner_radius=1)
        bar.pack(fill='x', padx=14, pady=(3, 6))

        self.body = ctk.CTkFrame(inner, fg_color='transparent')
        self.body.pack(fill='both', expand=True, padx=8, pady=(0, 8))

    def _sep(self, parent, row, cols):
        s = ctk.CTkFrame(parent, height=1, fg_color=C['border'])
        s.grid(row=row, column=0, columnspan=cols, padx=4, pady=3, sticky='ew')

    def _btn(self, parent, text, width, cmd, row, col, style='secondary', **kw):
        kw.setdefault('height', 30)
        b = ClaudeButton(parent, text=text, width=width, command=cmd, style=style, **kw)
        b.grid(row=row, column=col, padx=3, pady=2)
        return b

    def _lbl(self, parent, text, row, col, **kw):
        kw.setdefault('font', ('Segoe UI', 12))
        kw.setdefault('text_color', C['text'])
        l = ctk.CTkLabel(parent, text=text, **kw)
        l.grid(row=row, column=col, padx=4, pady=2, sticky='w')
        return l

    def _log(self, msg, level='INFO'):
        self.app.log(msg, level)

    def _on_close(self):
        ModalBase._open_count -= 1
        self.app._on_modal_closed(self)
        self.destroy()


# ─── Modals ───────────────────────────────────────────────────

class FirebaseModal(ModalBase):
    def __init__(self, parent, app):
        super().__init__(parent, app, 'Firebase', 620, 240)

        self.status_dots = {}
        card = self.body
        card.grid_columnconfigure(10, weight=1)

        r = -1

        r += 1
        self._lbl(card, 'Emulators', r, 0, font=('Segoe UI', 11), text_color=C['muted'])
        if app.config.use_emulators:
            self.btn_start = self._btn(card, '\u25B6  Start', 85,
                                        app._start_emulators, r, 2, 'primary')
            self.btn_stop = self._btn(card, '\u25A0  Stop', 65,
                                       app._stop_emulators, r, 3, 'danger', state='disabled')
            self.btn_restart = self._btn(card, '\u21BB  Restart', 80,
                                          app._restart_emulators, r, 4, 'warning', state='disabled')

        r += 1
        dots_frame = ctk.CTkFrame(card, fg_color='transparent')
        dots_frame.grid(row=r, column=2, columnspan=5, padx=4, pady=1, sticky='w')

        if app.config.use_emulators:
            ports = app.config.emulator_ports
            for i, (name, label) in enumerate([
                ('Auth', f'Auth:{ports["auth"]}'),
                ('Firestore', f'Firestore:{ports["firestore"]}'),
                ('Storage', f'Storage:{ports["storage"]}'),
                ('Emulator UI', f'Emulator UI:{ports["ui"]}'),
            ]):
                dot = StatusDot(dots_frame, label)
                dot.grid(row=0, column=i, padx=(0, 10))
                self.status_dots[name] = dot
        else:
            ctk.CTkLabel(dots_frame, text='Deployed mode \u2014 no local emulators',
                          font=('Segoe UI', 11), text_color=C['muted']).grid(row=0, column=0)

        r += 1; self._sep(card, r, 11)
        r += 1
        self._lbl(card, 'Auth', r, 0, font=('Segoe UI', 11), text_color=C['muted'])
        self._btn(card, '\u25C9  Login', 80, app._firebase_login, r, 2, 'primary')
        self._btn(card, '\u25C9  Logout', 80, app._firebase_logout, r, 3)

        r += 1; self._sep(card, r, 11)
        r += 1
        self._lbl(card, 'Deploy', r, 0, font=('Segoe UI', 11), text_color=C['muted'])
        app.deploy_target = ctk.StringVar(value='all')
        rf = ctk.CTkFrame(card, fg_color='transparent')
        rf.grid(row=r, column=1, columnspan=4, sticky='w')
        for i, (text, val) in enumerate([
            ('All', 'all'), ('Firestore', 'firestore'), ('Functions', 'functions'),
            ('Hosting', 'hosting'), ('Storage', 'storage'),
        ]):
            ctk.CTkRadioButton(
                rf, text=text, variable=app.deploy_target,
                value=val, font=('Segoe UI', 10),
            ).grid(row=0, column=i, padx=(1, 2), pady=1)

        app._btn_deploy = self._btn(card, '\u25B6  Deploy', 75,
                                     app._firebase_deploy, r, 5, 'primary')

    def update_dots(self, statuses):
        for name, alive in statuses.items():
            dot = self.status_dots.get(name)
            if dot:
                dot.set_alive(alive)


class FlutterModal(ModalBase):
    def __init__(self, parent, app):
        super().__init__(parent, app, 'Flutter', 620, 290)
        card = self.body
        card.grid_columnconfigure(10, weight=1)

        r = -1

        r += 1
        self._lbl(card, 'Run', r, 0, font=('Segoe UI', 11), text_color=C['muted'])
        app._btn_flutter_run = self._btn(card, '\u25B6  Run', 60,
                                          app._flutter_run, r, 2, 'primary')
        app._btn_flutter_stop = self._btn(card, '\u25A0  Stop', 55,
                                           app._flutter_stop, r, 3, 'danger', state='disabled')
        app._btn_hot_reload = self._btn(card, '\u21BB  Hot Reload', 95,
                                         app._hot_reload, r, 4, state='disabled')

        r += 1; self._sep(card, r, 11)
        r += 1
        self._lbl(card, 'Deps', r, 0, font=('Segoe UI', 11), text_color=C['muted'])
        self._btn(card, '\u2B07  Pub Get', 80, app._pub_get, r, 2)
        self._btn(card, '\u267B  Build Runner', 100, app._build_runner, r, 3)
        self._lbl(card, 'Device:', r, 5)
        devices = ['(auto)', 'windows', 'chrome', 'edge', 'android', 'ios', 'web']
        app.device_var = ctk.StringVar(value=app.config.flutter_device or '(auto)')
        app.device_combo = ctk.CTkComboBox(
            card, values=devices, variable=app.device_var, width=100,
            state='readonly', command=app._on_device_change,
            font=('Segoe UI', 11),
        )
        app.device_combo.grid(row=r, column=6, padx=2, pady=2)

        r += 1; self._sep(card, r, 11)
        r += 1
        self._lbl(card, 'Build', r, 0, font=('Segoe UI', 11), text_color=C['muted'])
        self._btn(card, '\uD83D\uDCE6  Build APK', 95, app._build_apk, r, 2, 'primary')
        self._btn(card, '\uD83D\uDD0D  Analyze', 80, app._analyze, r, 3)
        self._btn(card, '\uD83D\uDDD1  Clean', 65, app._clean, r, 4, 'warning')

        r += 1; self._sep(card, r, 11)
        r += 1
        self._lbl(card, 'Test', r, 0, font=('Segoe UI', 11), text_color=C['muted'])
        self._btn(card, '\uD83E\uDDEA  Test', 65, app._test, r, 2)
        self._btn(card, '\uD83C\uDFE5  Doctor', 75, app._doctor, r, 3)
        self._btn(card, '\u2B06  Upgrade', 80, app._flutter_upgrade, r, 4)

        r += 1; self._sep(card, r, 11)
        r += 1
        self._lbl(card, 'Utils', r, 0, font=('Segoe UI', 11), text_color=C['muted'])
        self._btn(card, '\u2B06  Pub Upgrade', 100, app._pub_upgrade, r, 2)
        self._btn(card, '\uD83D\uDD27  Dart Fix', 85, app._dart_fix, r, 3)
        self._btn(card, '\u2728  Dart Format', 100, app._dart_format, r, 4)
        app._btn_flutter_logs = self._btn(card, '\uD83D\uDCCB  Logs', 70,
                                           app._flutter_logs, r, 5)
        app._btn_stop_logs = self._btn(card, '\u23F9  Stop Logs', 85,
                                        app._stop_flutter_logs, r, 6, 'danger', state='disabled')


class AndroidModal(ModalBase):
    def __init__(self, parent, app):
        super().__init__(parent, app, 'Android Emulator', 480, 180)
        card = self.body
        card.grid_columnconfigure(3, weight=1)

        r = -1

        r += 1
        self._lbl(card, 'AVD', r, 0, font=('Segoe UI', 11), text_color=C['muted'])
        app.avd_combo = ctk.CTkComboBox(
            card, values=['(no AVDs found)'], width=260, state='readonly',
            font=('Segoe UI', 11),
        )
        app.avd_combo.grid(row=r, column=2, padx=2, pady=(4, 8), sticky='w')
        self._btn(card, '\u21BB', 35, app._init_avd_list, r, 3, font=('Segoe UI', 14))
        app.btn_avd_launch = self._btn(card, '\u25B6  Launch', 80,
                                        app._launch_avd, r, 4, 'primary')
        app.btn_avd_kill = self._btn(card, '\u25A0  Kill', 65,
                                      app._kill_avd, r, 5, 'danger', state='disabled')

        r += 1; self._sep(card, r, 6)
        r += 1
        self._lbl(card, 'Links', r, 0, font=('Segoe UI', 11), text_color=C['muted'])
        self._btn(card, '\uD83C\uDF10  Emulator UI', 110,
                  app.controller.open_emulator_ui, r, 2)
        self._btn(card, '\uD83D\uDD25  Firestore', 95,
                  app.controller.open_firestore_console, r, 3)
        self._btn(card, '\uD83D\uDCE6  Install APK', 105,
                  app._adb_install, r, 4)

        app._init_avd_list()


class GitModal(ModalBase):
    def __init__(self, parent, app):
        super().__init__(parent, app, 'Git', 520, 240)
        card = self.body
        card.grid_columnconfigure(2, weight=1)

        r = -1

        r += 1
        self._lbl(card, 'Msg', r, 0, font=('Segoe UI', 11), text_color=C['muted'])
        app.git_msg_entry = ctk.CTkEntry(
            card, placeholder_text='Enter commit message...', font=('Segoe UI', 12))
        app.git_msg_entry.grid(row=r, column=2, columnspan=3, padx=2, pady=(4, 8), sticky='ew')

        self._btn(card, '\u2795  Add & Commit', 120, app._git_commit, r, 5, 'primary')
        self._btn(card, '\u2B07  Pull', 65, app._git_pull, r, 6)
        self._btn(card, '\u2B06  Push', 65, app._git_push, r, 7)

        r += 1; self._sep(card, r, 9)
        r += 1
        self._lbl(card, 'Info', r, 0, font=('Segoe UI', 11), text_color=C['muted'])
        self._btn(card, '\u2139  Status', 75, app._git_status, r, 2)
        self._btn(card, '\uD83D\uDCCB  Log', 65, app._git_log, r, 3)
        self._btn(card, '\uD83C\uDFF7  Branch', 80, app._git_branch, r, 4)

        r += 1; self._sep(card, r, 9)
        r += 1
        self._lbl(card, 'Sync', r, 0, font=('Segoe UI', 11), text_color=C['muted'])
        self._btn(card, '\uD83D\uDD04  Fetch', 75, app._git_fetch, r, 2)
        self._btn(card, '\uD83D\uDCE4  Stash', 75, app._git_stash, r, 3)
        self._btn(card, '\uD83D\uDCE5  Stash Pop', 95, app._git_stash_pop, r, 4)


class ToolsModal(ModalBase):
    def __init__(self, parent, app):
        super().__init__(parent, app, 'Tools', 520, 300)
        card = self.body
        card.grid_columnconfigure(6, weight=1)

        r = -1

        r += 1
        self._lbl(card, 'Nav', r, 0, font=('Segoe UI', 11), text_color=C['muted'])
        self._btn(card, '\uD83C\uDF10  Emulator UI', 115,
                  app.controller.open_emulator_ui, r, 2)
        self._btn(card, '\uD83D\uDD25  Firestore', 95,
                  app.controller.open_firestore_console, r, 3)
        self._btn(card, '\uD83D\uDCC2  Project Folder', 120,
                  app.controller.open_project_folder, r, 4)
        self._btn(card, '\u2699  Settings', 80, app._open_settings, r, 5)
        self._btn(card, '\uD83D\uDD04  Switch Project', 125, app._switch_project, r, 6)

        r += 1; self._sep(card, r, 8)
        r += 1
        self._lbl(card, 'Env', r, 0, font=('Segoe UI', 11), text_color=C['muted'])
        app.env_combo = ctk.CTkComboBox(
            card, values=['default', 'staging', 'production'],
            width=120, state='readonly',
            font=('Segoe UI', 11), command=app._on_env_change,
        )
        app.env_combo.set('default')
        app.env_combo.grid(row=r, column=2, padx=2, pady=(2, 8))

        r += 1; self._sep(card, r, 8)
        r += 1
        self._lbl(card, 'Data', r, 0, font=('Segoe UI', 11), text_color=C['muted'])
        self._btn(card, '\uD83D\uDD14  Test Notification', 135,
                  app._test_notification, r, 2)
        self._btn(card, '\uD83D\uDCE4  Export Data', 110, app._export_data, r, 3)
        self._btn(card, '\uD83D\uDCE5  Import Data', 110, app._import_data, r, 4)

        r += 1; self._sep(card, r, 8)
        r += 1
        self._lbl(card, 'Npm', r, 0, font=('Segoe UI', 11), text_color=C['muted'])
        app._npm_script_var = ctk.StringVar()
        ctk.CTkEntry(
            card, textvariable=app._npm_script_var, width=100,
            placeholder_text='script...', font=('Segoe UI', 11),
        ).grid(row=r, column=2, padx=2, pady=2)
        self._btn(card, '\u25B6  Run', 55, app._npm_run, r, 3)
        self._btn(card, '\u2B07  Install', 75, app._npm_install, r, 4)
        self._btn(card, '\uD83E\uDDEA  Test', 65, app._npm_test, r, 5)
        self._btn(card, '\uD83D\uDD0D  Audit', 70, app._npm_audit, r, 6)
        self._btn(card, '\uD83D\uDDC4  Outdated', 85, app._npm_outdated, r, 7)


# ─── Main App ─────────────────────────────────────────────────

class PetTrackerDevTool(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title('Dev Toolkit')
        self.configure(fg_color=C['bg'])

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w = sw // 2
        h = sh - 80
        self.geometry(f'{w}x{h}+0+0')
        self.minsize(w, h)
        self.maxsize(w, h)
        self.protocol('WM_DELETE_WINDOW', self._on_close)

        self.config = Config()
        if not self.config.load():
            self._run_setup()
            if not self.config.is_valid:
                self.destroy()
                return

        self._git_branch = ''
        self._flutter_version = ''
        self._modals = []

        self._setup_grid()
        self._build_header()
        self._build_launcher()
        self._build_terminal()
        self._build_log_panel()

        self.logger = LogHandler(self.log_textbox)
        self.controller = ProcessController(self.config, self.log, self.after)

        self.monitor = ServiceMonitor(self._on_status_change, self.config)
        self.monitor.start()
        self._build_status_bar()
        self._build_command_map()
        self.bind_all('<Control-p>', lambda e: self._open_palette())

        self.log('Dev Toolkit ready.', 'SUCCESS')
        self.log(f'Project: {self.config.project_root}', 'INFO')
        self._update_git_branch()
        self._update_flutter_version()

    # ── Layout ─────────────────────────────────────────────

    def _setup_grid(self):
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)
        self.grid_rowconfigure(3, weight=0)

    def _build_header(self):
        h = ctk.CTkFrame(self, corner_radius=0, height=36, fg_color=C['card'])
        h.grid(row=0, column=0, columnspan=2, sticky='ew')
        h.grid_propagate(False)
        h.grid_columnconfigure(2, weight=1)

        bar = ctk.CTkFrame(h, height=2, fg_color=C['accent'], corner_radius=0)
        bar.grid(row=1, column=0, columnspan=4, sticky='ew')

        ctk.CTkLabel(h, text='Dev Toolkit', font=('Segoe UI', 15, 'bold'),
                      text_color=C['accent']).grid(row=0, column=0, padx=(14, 6), pady=6, sticky='w')
        self.branch_label = ctk.CTkLabel(h, text='', font=('Consolas', 10),
                                          text_color=C['muted'])
        self.branch_label.grid(row=0, column=1, padx=(4, 8), pady=6, sticky='w')
        self.overall_status = ctk.CTkLabel(h, text='\u25CF  Idle', font=('Consolas', 11),
                                            text_color=C['muted'])
        self.overall_status.grid(row=0, column=3, padx=(8, 14), pady=6, sticky='e')

    # ── Launcher ───────────────────────────────────────────

    def _build_launcher(self):
        side = ctk.CTkFrame(self, width=280, fg_color=C['card'], corner_radius=8)
        side.grid(row=1, column=0, sticky='ns', padx=(6, 2), pady=(6, 2))
        side.grid_propagate(False)
        side.grid_columnconfigure(0, weight=1)

        r = -1
        r += 1; ctk.CTkLabel(side, text='  Launcher', font=('Segoe UI', 13, 'bold'),
                              text_color=C['text']).grid(row=r, column=0, padx=8, pady=(12, 4), sticky='w')
        r += 1; ctk.CTkFrame(side, height=2, fg_color=C['accent'], corner_radius=1
                             ).grid(row=r, column=0, sticky='ew', padx=14, pady=(0, 8))

        sections = [
            ('Firebase', '\uD83D\uDD25', self._open_firebase),
            ('Flutter', '\u2699', self._open_flutter),
            ('Android Emulator', '\uD83D\uDCF1', self._open_android),
            ('Git', '\uD83D\uDDC2', self._open_git),
            ('Tools', '\uD83D\uDEE0', self._open_tools),
        ]

        self._launch_btns = {}
        for label, icon, cmd in sections:
            r += 1
            btn = ClaudeButton(
                side, text=f'{icon}  {label}',
                width=200, height=42,
                font=('Segoe UI', 14),
                command=cmd,
                style='secondary',
                corner_radius=6,
            )
            btn.grid(row=r, column=0, pady=4)
            self._launch_btns[label] = btn

        r += 1; ctk.CTkFrame(side, height=1, fg_color=C['border']
                             ).grid(row=r, column=0, sticky='ew', padx=14, pady=(8, 2))
        r += 1; ctk.CTkLabel(side, text='  Project Root', font=('Segoe UI', 11, 'bold'),
                              text_color=C['text']).grid(row=r, column=0, padx=8, pady=(4, 2), sticky='w')
        r += 1; ctk.CTkFrame(side, height=1, fg_color=C['accent'], corner_radius=1
                             ).grid(row=r, column=0, sticky='ew', padx=14, pady=(0, 6))

        r += 1
        root_path = self.config.project_root if self.config and self.config.project_root else '(not set)'
        self._path_label = ctk.CTkLabel(side, text=self._truncate_path(root_path),
                                         font=('Consolas', 10),
                                         text_color=C['muted'], anchor='w')
        self._path_label.grid(row=r, column=0, padx=10, pady=(0, 2), sticky='ew')

        r += 1
        pbtn_frame = ctk.CTkFrame(side, fg_color='transparent')
        pbtn_frame.grid(row=r, column=0, pady=(0, 4))
        ClaudeButton(pbtn_frame, text='Browse', width=85, height=28, style='secondary',
                      font=('Segoe UI', 10), command=self._browse_project).pack(side='left', padx=4)
        ClaudeButton(pbtn_frame, text='Open', width=85, height=28, style='secondary',
                      font=('Segoe UI', 10),
                      command=lambda: self.controller.open_project_folder()).pack(side='left', padx=4)

        side.grid_rowconfigure(r + 1, weight=1)

    def _build_terminal(self):
        root = self.config.project_root if self.config and self.config.project_root else os.getcwd()
        self.terminal = TerminalWidget(self, root)
        self.terminal.grid(row=1, column=1, sticky='nsew', padx=(4, 4), pady=(4, 0))

    def _open_modal(self, cls, btn_key=None):
        for m in self._modals:
            if isinstance(m, cls):
                m.lift()
                m.focus()
                return
        modal = cls(self, self)
        modal._btn_key = btn_key
        self._modals.append(modal)
        if btn_key and btn_key in self._launch_btns:
            self._launch_btns[btn_key].configure(
                fg_color=C['accent'], hover_color=C['accent_h'],
                text_color=C['bg'],
            )

    def _on_modal_closed(self, modal):
        if modal in self._modals:
            self._modals.remove(modal)
        btn_key = getattr(modal, '_btn_key', None)
        if btn_key and btn_key in self._launch_btns:
            self._launch_btns[btn_key].configure(
                fg_color=C['gray'], hover_color=C['gray_h'],
                text_color=C['text'],
            )

    def _open_firebase(self):
        self._open_modal(FirebaseModal, btn_key='Firebase')

    def _open_flutter(self):
        self._open_modal(FlutterModal, btn_key='Flutter')

    def _open_android(self):
        self._open_modal(AndroidModal, btn_key='Android Emulator')

    def _open_git(self):
        self._open_modal(GitModal, btn_key='Git')

    def _open_tools(self):
        self._open_modal(ToolsModal, btn_key='Tools')

    # ── Command Palette ─────────────────────────────────────

    def _build_command_map(self):
        self._cmd_map = {
            'Firebase \u2014 Open Modal': self._open_firebase,
            'Firebase \u2014 Deploy All': lambda: self._firebase_deploy_target('all'),
            'Firebase \u2014 Deploy Firestore': lambda: self._firebase_deploy_target('firestore'),
            'Firebase \u2014 Deploy Functions': lambda: self._firebase_deploy_target('functions'),
            'Firebase \u2014 Deploy Hosting': lambda: self._firebase_deploy_target('hosting'),
            'Firebase \u2014 Deploy Storage': lambda: self._firebase_deploy_target('storage'),
            'Firebase \u2014 Login': self._firebase_login,
            'Firebase \u2014 Logout': self._firebase_logout,
            'Firebase \u2014 Start Emulators': self._start_emulators,
            'Firebase \u2014 Stop Emulators': self._stop_emulators,
            'Firebase \u2014 Restart Emulators': self._restart_emulators,
            'Flutter \u2014 Open Modal': self._open_flutter,
            'Flutter \u2014 Run': self._flutter_run,
            'Flutter \u2014 Stop': self._flutter_stop,
            'Flutter \u2014 Hot Reload': self._hot_reload,
            'Flutter \u2014 Pub Get': self._pub_get,
            'Flutter \u2014 Build Runner': self._build_runner,
            'Flutter \u2014 Build APK': self._build_apk,
            'Flutter \u2014 Analyze': self._analyze,
            'Flutter \u2014 Clean': self._clean,
            'Flutter \u2014 Test': self._test,
            'Flutter \u2014 Doctor': self._doctor,
            'Flutter \u2014 Upgrade': self._flutter_upgrade,
            'Flutter \u2014 Pub Upgrade': self._pub_upgrade,
            'Flutter \u2014 Dart Fix': self._dart_fix,
            'Flutter \u2014 Dart Format': self._dart_format,
            'Flutter \u2014 Logs': self._flutter_logs,
            'Flutter \u2014 Stop Logs': self._stop_flutter_logs,
            'Android \u2014 Open Modal': self._open_android,
            'Android \u2014 Launch AVD': self._launch_avd,
            'Android \u2014 Kill AVD': self._kill_avd,
            'Android \u2014 Install APK': self._adb_install,
            'Android \u2014 Emulator UI': lambda: self.controller.open_emulator_ui(),
            'Android \u2014 Firestore Console': lambda: self.controller.open_firestore_console(),
            'Git \u2014 Open Modal': self._open_git,
            'Git \u2014 Add & Commit': self._git_commit,
            'Git \u2014 Pull': self._git_pull,
            'Git \u2014 Push': self._git_push,
            'Git \u2014 Status': self._git_status,
            'Git \u2014 Log': self._git_log,
            'Git \u2014 Branch': self._git_branch,
            'Git \u2014 Fetch': self._git_fetch,
            'Git \u2014 Stash': self._git_stash,
            'Git \u2014 Stash Pop': self._git_stash_pop,
            'Tools \u2014 Open Modal': self._open_tools,
            'Tools \u2014 Settings': self._open_settings,
            'Tools \u2014 Switch Project': self._switch_project,
            'Tools \u2014 Test Notification': self._test_notification,
            'Tools \u2014 Export Data': self._export_data,
            'Tools \u2014 Import Data': self._import_data,
            'Tools \u2014 npm Install': self._npm_install,
            'Tools \u2014 npm Test': self._npm_test,
            'Tools \u2014 npm Audit': self._npm_audit,
            'Tools \u2014 npm Outdated': self._npm_outdated,
        }

    def _open_palette(self):
        CommandPalette(self, self._cmd_map)

    # ── Helpers ────────────────────────────────────────────

    def _update_git_branch(self):
        def _run():
            b = self.controller.get_git_branch()
            if b:
                self.after(0, lambda: self.branch_label.configure(text=f'\uE0A0  {b}'))
        threading.Thread(target=_run, daemon=True).start()

    def _update_flutter_version(self):
        def _run():
            v = self.controller.get_flutter_version()
            if v:
                self._flutter_version = v
                self.after(0, self._refresh_status_bar)
        threading.Thread(target=_run, daemon=True).start()

    def _run_setup(self):
        self.withdraw()
        self.config.auto_detect()
        dialog = SetupDialog(self, self.config)
        self.wait_window(dialog)
        if dialog.result:
            self.config = dialog.result
        self.deiconify()

    # ── Firebase ───────────────────────────────────────────

    def _start_emulators(self):
        self._log('Starting Firebase Emulators...', 'INFO')
        self.controller.start_emulators()

    def _stop_emulators(self):
        self._log('Stopping Firebase Emulators...', 'INFO')
        self.controller.stop_emulators()

    def _restart_emulators(self):
        self._log('Restarting Firebase Emulators...', 'INFO')
        self.controller.stop_emulators(on_done=self._start_emulators)

    def _firebase_login(self):
        self._log('Opening Firebase login...', 'INFO')
        self.controller.firebase_login()

    def _firebase_logout(self):
        self._log('Signing out of Firebase...', 'INFO')
        self.controller.firebase_logout()

    def _firebase_deploy_target(self, target):
        self._log(f'Firebase deploy: {target}', 'INFO')
        if hasattr(self, '_btn_deploy') and self._btn_deploy:
            self._btn_deploy.configure(state='disabled', text='\u25B6  Deploying...')

        def on_done():
            if hasattr(self, '_btn_deploy') and self._btn_deploy:
                self._btn_deploy.configure(state='normal', text='\u25B6  Deploy')

        def _run():
            if target == 'all':
                self.controller.firebase_deploy(on_done=on_done)
            else:
                self.controller.firebase_deploy(target=target, on_done=on_done)
        threading.Thread(target=_run, daemon=True).start()

    def _firebase_deploy(self):
        target = self.deploy_target.get()
        if hasattr(self, '_btn_deploy') and self._btn_deploy:
            self._btn_deploy.configure(state='disabled', text='\u25B6  Deploying...')
        self._log(f'Firebase deploy: {target}', 'INFO')

        def on_done():
            if hasattr(self, '_btn_deploy') and self._btn_deploy:
                self._btn_deploy.configure(state='normal', text='\u25B6  Deploy')

        self.controller.firebase_deploy(target, on_done=on_done)

    # ── Flutter ────────────────────────────────────────────

    def _on_device_change(self, choice):
        self.config.flutter_device = '' if choice == '(auto)' else choice
        self.config.save()

    def _flutter_run(self):
        if hasattr(self, '_btn_flutter_run') and self._btn_flutter_run:
            self._btn_flutter_run.configure(state='disabled', text='\u25B6  Starting...')
            self._btn_hot_reload.configure(state='disabled')

        def on_start():
            if hasattr(self, '_btn_flutter_run') and self._btn_flutter_run:
                self._btn_flutter_run.configure(text='\u25B6  Run')
                self._btn_flutter_stop.configure(state='normal')
                self._btn_hot_reload.configure(state='normal')

        def on_done():
            if hasattr(self, '_btn_flutter_run') and self._btn_flutter_run:
                self._btn_flutter_run.configure(state='normal', text='\u25B6  Run')
                self._btn_flutter_stop.configure(state='disabled')
                self._btn_hot_reload.configure(state='disabled')

        self.controller.flutter_run(on_start=on_start, on_done=on_done)

    def _flutter_stop(self):
        if hasattr(self, '_btn_flutter_stop') and self._btn_flutter_stop:
            self._btn_flutter_stop.configure(state='disabled')
            self._btn_hot_reload.configure(state='disabled')

        def _reset():
            if hasattr(self, '_btn_flutter_run') and self._btn_flutter_run:
                self._btn_flutter_run.configure(state='normal', text='\u25B6  Run')
                self._btn_flutter_stop.configure(state='disabled')
                self._btn_hot_reload.configure(state='disabled')
        self.controller.stop_flutter(on_done=lambda: self.after(0, _reset))

    def _hot_reload(self):
        self.controller.flutter_hot_reload()

    def _pub_get(self):
        self._log('Running flutter pub get...', 'INFO')
        self.controller.flutter_pub_get()

    def _build_runner(self):
        self._log('Running build_runner...', 'INFO')
        self.controller.build_runner()

    def _build_apk(self):
        self._log('Building APK...', 'INFO')
        self.controller.flutter_build_apk()

    def _analyze(self):
        self._log('Running flutter analyze...', 'INFO')
        self.controller.flutter_analyze()

    def _clean(self):
        if messagebox.askyesno('Clean', 'Remove build/ and run pub get?'):
            self._log('Cleaning project...', 'INFO')
            self.controller.flutter_clean()

    def _test(self):
        self._log('Running flutter test...', 'INFO')
        self.controller.flutter_test()

    def _doctor(self):
        self._log('Running flutter doctor...', 'INFO')
        self.controller.flutter_doctor()

    def _flutter_upgrade(self):
        self._log('Running flutter upgrade...', 'INFO')
        self.controller.flutter_upgrade()

    def _pub_upgrade(self):
        self._log('Running pub upgrade...', 'INFO')
        self.controller.pub_upgrade()

    def _dart_fix(self):
        self._log('Running dart fix...', 'INFO')
        self.controller.dart_fix()

    def _dart_format(self):
        self._log('Running dart format...', 'INFO')
        self.controller.dart_format()

    def _flutter_logs(self):
        if hasattr(self, '_btn_flutter_logs') and self._btn_flutter_logs:
            self._btn_flutter_logs.configure(state='disabled', text='\uD83D\uDCCB  Logs...')
            self._btn_stop_logs.configure(state='normal')
        self._log('Starting flutter logs...', 'INFO')

        def on_done():
            if hasattr(self, '_btn_flutter_logs') and self._btn_flutter_logs:
                self._btn_flutter_logs.configure(state='normal', text='\uD83D\uDCCB  Logs')
                self._btn_stop_logs.configure(state='disabled')
        self.controller.flutter_logs(on_start=lambda: None, on_done=on_done)

    def _stop_flutter_logs(self):
        if hasattr(self, '_btn_stop_logs') and self._btn_stop_logs:
            self._btn_stop_logs.configure(state='disabled')

        def _reset():
            if hasattr(self, '_btn_flutter_logs') and self._btn_flutter_logs:
                self._btn_flutter_logs.configure(state='normal', text='\uD83D\uDCCB  Logs')
                self._btn_stop_logs.configure(state='disabled')
        self.controller.stop_flutter_logs(on_done=lambda: self.after(0, _reset))

    # ── npm ────────────────────────────────────────────────

    def _npm_install(self):
        self._log('Running npm install...', 'INFO')
        self.controller.npm_install()

    def _npm_run(self):
        script = getattr(self, '_npm_script_var', None)
        if script and script.get():
            self._log(f'Running npm run {script.get()}...', 'INFO')
            self.controller.npm_run(script.get())
        else:
            self._log('No npm script specified.', 'WARNING')

    def _npm_test(self):
        self._log('Running npm test...', 'INFO')
        self.controller.npm_test()

    def _npm_audit(self):
        self._log('Running npm audit...', 'INFO')
        self.controller.npm_audit()

    def _npm_outdated(self):
        self._log('Running npm outdated...', 'INFO')
        self.controller.npm_outdated()

    # ── Android ────────────────────────────────────────────

    def _init_avd_list(self):
        def _run():
            avds = self.controller.list_avds()
            self.after(0, lambda: self._populate_avds(avds))
        threading.Thread(target=_run, daemon=True).start()

    def _populate_avds(self, avds):
        if hasattr(self, 'avd_combo') and self.avd_combo:
            if avds:
                self.avd_combo.configure(values=avds)
                self.avd_combo.set(avds[0])
            else:
                self.avd_combo.configure(values=['(no AVDs found)'])
                self.avd_combo.set('(no AVDs found)')

    def _launch_avd(self):
        name = self.avd_combo.get() if hasattr(self, 'avd_combo') else ''
        if not name or name == '(no AVDs found)':
            self._log('No AVD selected.', 'WARNING')
            return
        if hasattr(self, 'btn_avd_launch') and self.btn_avd_launch:
            self.btn_avd_launch.configure(state='disabled', text='\u25B6  Launching...')
        self._log(f'Launching Android emulator: {name}', 'INFO')

        def on_start():
            if hasattr(self, 'btn_avd_launch') and self.btn_avd_launch:
                self.btn_avd_launch.configure(text='\u25B6  Launch')
                self.btn_avd_kill.configure(state='normal')
                self.avd_combo.configure(state='disabled')

        def on_done():
            if hasattr(self, 'btn_avd_launch') and self.btn_avd_launch:
                self.btn_avd_launch.configure(state='normal', text='\u25B6  Launch')
                self.btn_avd_kill.configure(state='disabled')
                self.avd_combo.configure(state='readonly')

        self.controller.launch_avd(name, on_start=on_start, on_done=on_done)

    def _kill_avd(self):
        if hasattr(self, 'btn_avd_kill') and self.btn_avd_kill:
            self.btn_avd_kill.configure(state='disabled')
        self._log('Stopping Android emulator...', 'INFO')

        def _reset():
            if hasattr(self, 'btn_avd_launch') and self.btn_avd_launch:
                self.btn_avd_launch.configure(state='normal')
                self.btn_avd_kill.configure(state='disabled')
                self.avd_combo.configure(state='readonly')
        self.controller.kill_avd(on_done=lambda: self.after(0, _reset))

    def _adb_install(self):
        path = filedialog.askopenfilename(
            title='Select APK to install',
            filetypes=[('APK files', '*.apk'), ('All files', '*.*')],
        )
        if not path:
            return
        self._log(f'Installing APK via ADB: {os.path.basename(path)}', 'INFO')
        self.controller.adb_install(path)

    # ── Git ────────────────────────────────────────────────

    def _git_commit(self):
        msg = self.git_msg_entry.get().strip() if hasattr(self, 'git_msg_entry') else ''
        if not msg:
            messagebox.showwarning('Commit', 'Please enter a commit message.')
            return
        self._log(f'Git: add & commit \u2014 "{msg}"', 'INFO')
        self.git_msg_entry.delete(0, 'end')

        def do_add():
            self.controller.git_add_all()
            self.controller.git_commit(msg)
        threading.Thread(target=do_add, daemon=True).start()

    def _git_status(self):
        self._log('Git: status...', 'INFO')
        self.controller.git_status()

    def _git_log(self):
        self._log('Git: log...', 'INFO')
        self.controller.git_log()

    def _git_fetch(self):
        self._log('Git: fetch...', 'INFO')
        self.controller.git_fetch()

    def _git_stash(self):
        self._log('Git: stash...', 'INFO')
        self.controller.git_stash()

    def _git_stash_pop(self):
        self._log('Git: stash pop...', 'INFO')
        self.controller.git_stash_pop()

    def _git_branch(self):
        self._log('Git: branch...', 'INFO')
        self.controller.git_branch()

    def _git_pull(self):
        self._log('Git: pull...', 'INFO')
        self.controller.git_pull()

    def _git_push(self):
        self._log('Git: push...', 'INFO')
        self.controller.git_push()

    # ── Tools ──────────────────────────────────────────────

    def _open_settings(self):
        dialog = SetupDialog(self, self.config)
        self.wait_window(dialog)
        if dialog.result:
            self.config = dialog.result
            self.controller.config = self.config
            self._log('Settings updated.', 'INFO')
            self._init_avd_list()

    def _reconfigure_after_path_change(self, path):
        self.config.project_root = path
        self.config.auto_detect(project_root_hint=path)
        self.config.save()
        self.controller.config = self.config
        if hasattr(self, 'terminal'):
            self.terminal.project_root = path
            self.terminal._prompt_prefix = f'{path}>'
            self.terminal._write(f'\nSwitched to: {path}\n', 'prompt')
        self._update_path_label()
        self._log(f'Switched to project: {path}', 'INFO')
        self._init_avd_list()
        self._update_git_branch()
        self._update_flutter_version()
        self._refresh_status_bar()

    def _truncate_path(self, path, max_len=35):
        return path if len(path) <= max_len else path[:12] + '...' + path[-(max_len - 15):]

    def _update_path_label(self):
        if hasattr(self, '_path_label'):
            root = self.config.project_root or '(not set)'
            self._path_label.configure(text=self._truncate_path(root))

    def _browse_project(self):
        path = filedialog.askdirectory(title='Select Flutter project root')
        if not path:
            return
        if not os.path.isfile(os.path.join(path, 'pubspec.yaml')):
            messagebox.showerror('Error', 'Selected folder does not contain a pubspec.yaml.')
            return
        self._reconfigure_after_path_change(path)

    def _switch_project(self):
        self._browse_project()

    def _on_env_change(self, choice):
        self._log(f'Switching Firebase environment to: {choice}', 'INFO')
        self.controller.switch_firebase_project(choice)

    def _test_notification(self):
        NotifyDialog(self, self._do_send_notification)

    def _do_send_notification(self, token, title, body):
        self._log('Sending test notification...', 'INFO')
        self.controller.send_test_notification(token, title or '(no title)', body or '(no body)')

    def _export_data(self):
        path = filedialog.askdirectory(title='Select export directory')
        if not path:
            return
        self._log(f'Exporting emulator data to {path}...', 'INFO')
        self.controller.firebase_export_data(path)

    def _import_data(self):
        path = filedialog.askdirectory(title='Select import directory')
        if not path:
            return
        self._log(f'Importing emulator data from {path}...', 'INFO')
        self.controller.firebase_import_data(path)

    # ── Log Panel ──────────────────────────────────────────

    def _build_log_panel(self):
        container = ctk.CTkFrame(self, border_width=1, border_color=C['border'],
                                  fg_color=C['card'])
        container.grid(row=2, column=0, columnspan=2, padx=10, pady=(4, 6), sticky='nsew')
        container.grid_rowconfigure(1, weight=1)
        container.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(container, fg_color='transparent')
        header.grid(row=0, column=0, sticky='ew')
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(header, text='Log Output',
                      font=('Segoe UI', 11, 'bold'), text_color=C['text'],
                      ).grid(row=0, column=0, padx=8, pady=(4, 2), sticky='w')

        ClaudeButton(header, text='Clear', width=55, height=22,
                      font=('Segoe UI', 10),
                      command=self._clear_log).grid(row=0, column=1, padx=(0, 8), pady=(5, 2), sticky='e')

        self.log_textbox = Text(
            container, bg='#18181c', fg='#c0c0c0',
            insertbackground='#c0c0c0', font=('Consolas', 11),
            relief='flat', borderwidth=0, padx=8, pady=6, wrap='word', state='normal',
        )
        self.log_textbox.grid(row=1, column=0, sticky='nsew', padx=0, pady=0)

        for tag, color in [
            ('info', '#c0c0c0'), ('success', '#4CAF50'), ('warning', '#FF9800'),
            ('error', '#F44336'), ('emulator', '#00BCD4'), ('flutter', '#FFD740'),
            ('android', '#81C784'), ('build', '#CE93D8'),
        ]:
            self.log_textbox.tag_config(tag, foreground=color)

    def _toast(self, msg):
        x = self.winfo_rootx() + self.winfo_width() - 300
        y = self.winfo_rooty() + self.winfo_height() - 80
        win = ctk.CTkToplevel(self)
        win.overrideredirect(True)
        win.geometry(f'280x36+{x}+{y}')
        win.attributes('-topmost', True)
        win.configure(fg_color=C['card'])
        win.attributes('-alpha', 0.95)
        ctk.CTkLabel(win, text=msg, font=('Segoe UI', 11), text_color='#4CAF50'
                     ).pack(padx=12, pady=6)
        win.after(3000, win.destroy)

    def _log(self, text, level='INFO'):
        self.logger.log(text, level)
        if level == 'SUCCESS':
            try:
                self._toast(text)
            except Exception:
                pass

    def log(self, text, level='INFO'):
        self.logger.log(text, level)

    def _clear_log(self):
        self.log_textbox.delete('1.0', 'end')

    # ── Status ─────────────────────────────────────────────

    def _build_status_bar(self):
        bar = ctk.CTkFrame(self, corner_radius=0, height=30, fg_color=C['card'])
        bar.grid(row=3, column=0, columnspan=2, sticky='ew')
        bar.grid_columnconfigure(2, weight=1)
        bar.grid_propagate(False)

        top_line = ctk.CTkFrame(bar, height=1, fg_color=C['border'], corner_radius=0)
        top_line.grid(row=0, column=0, columnspan=4, sticky='ew')

        self.abort_btn = ClaudeButton(bar, text='\u2716  Abort', width=75, style='danger',
                                      font=('Segoe UI', 10), height=24)
        self.abort_btn.configure(command=self._abort)
        self.abort_btn.grid(row=0, column=0, padx=(8, 4), pady=3)

        self.busy_indicator = ctk.CTkLabel(bar, text='', font=('Consolas', 11))
        self.busy_indicator.grid(row=0, column=1, padx=(0, 4), pady=3, sticky='w')

        parts = []
        if self._flutter_version:
            parts.append(f'Flutter: {self._flutter_version}')
        if self.config.android_sdk:
            parts.append(f'SDK: {os.path.basename(self.config.android_sdk)}')
        if self.config.java_home:
            parts.append(f'JDK: {os.path.basename(self.config.java_home)}')
        parts.append('Emulators' if self.config.use_emulators else 'Deployed')

        if not hasattr(self, 'status_label'):
            self.status_label = ctk.CTkLabel(bar, text='', font=('Segoe UI', 10),
                                              text_color=C['muted'])
            self.status_label.grid(row=0, column=2, padx=10, pady=3, sticky='w')
            self.status_label2 = ctk.CTkLabel(bar, text='', font=('Segoe UI', 10),
                                               text_color=C['muted'])
            self.status_label2.grid(row=0, column=3, padx=10, pady=3, sticky='e')

        self.status_label.configure(text='  |  '.join(parts))
        self.status_label2.configure(
            text='Port monitor active' if self.config.use_emulators else '')
        self._poll_busy()

    def _busy_dots(self, count):
        return '\u25CF' if count > 0 else ''

    def _poll_busy(self):
        busy = self.controller.is_busy() if hasattr(self, 'controller') else False
        color = C['accent'] if busy else C['muted']
        text = '\u25CF' if busy else '\u25CB'
        self.busy_indicator.configure(text=text, text_color=color)
        self.after(500, self._poll_busy)

    def _refresh_status_bar(self):
        self._build_status_bar()

    def _on_status_change(self, statuses):
        self.after(0, lambda: self._apply_status(statuses))

    def _apply_status(self, statuses):
        for modal in self._modals:
            if isinstance(modal, FirebaseModal) and modal.winfo_exists():
                modal.update_dots(statuses)
        self._update_overall_status()

    def _update_overall_status(self):
        alive = 0
        total = 0
        for modal in self._modals:
            if isinstance(modal, FirebaseModal) and modal.winfo_exists():
                for dot in modal.status_dots.values():
                    total += 1
                    if dot._alive:
                        alive += 1
        if total == 0:
            self.overall_status.configure(text='\u25CF  Idle', text_color=C['muted'])
        elif alive == total:
            self.overall_status.configure(text='\u25CF  All Running', text_color='#4CAF50')
        else:
            self.overall_status.configure(text='\u25CF  Partial', text_color='#FF9800')

    # ── Abort ──────────────────────────────────────────────

    def _abort(self):
        self._log('Abort requested — killing all processes...', 'WARNING')
        self.controller.abort_all()

    # ── Shutdown ───────────────────────────────────────────

    def _on_close(self):
        self._log('Shutting down...', 'INFO')
        self.monitor.stop()
        self.logger.stop()
        for modal in self._modals[:]:
            if modal.winfo_exists():
                modal.destroy()
        self._modals.clear()
        self.controller.kill_all()
        if hasattr(self, 'terminal'):
            self.terminal._abort_cmd()
        self.destroy()


if __name__ == '__main__':
    app = PetTrackerDevTool()
    app.mainloop()
