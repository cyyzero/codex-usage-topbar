#!/usr/bin/python3
"""GNOME top-panel indicator for the signed-in Codex usage."""
import ctypes
import ctypes.util
import datetime as dt
import fcntl
import json
import os
import signal
import threading

import gi

gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk

from usage import UsageClient


CONFIG_PATH = os.path.join(
    os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config')),
    'codex-usage-topbar',
    'config.json',
)

TEXT = {
    'zh': {
        'week': '周', 'unknown': '未知', 'subscription': '订阅',
        'used': '已用', 'reset': '重置', 'updated': '上次更新',
        'every_minute': '实时更新；每 30 分钟兜底刷新', 'local_time': '重置时间为本地时间',
        'stale': '⚠ 数据可能过期：', 'unavailable': 'Codex · 暂时无法读取',
        'waiting': '等待数据', 'login': '请确认 Codex 已登录',
        'retry': '请在网络恢复后手动刷新', 'manual': '菜单可手动刷新',
        'refresh': '立即刷新', 'language': '语言 / Language',
        'quit': '退出', 'loading': '正在读取…', 'short': '短期', 'long': '长期',
    },
    'en': {
        'week': 'W', 'unknown': 'Unknown', 'subscription': 'Subscription',
        'used': 'Used', 'reset': 'Resets', 'updated': 'Last updated',
        'every_minute': 'Live updates; 30 min fallback', 'local_time': 'Reset times are local',
        'stale': '⚠ Data may be stale: ', 'unavailable': 'Codex · unavailable',
        'waiting': 'Waiting for data', 'login': 'Make sure Codex is signed in',
        'retry': 'Refresh manually after the network recovers', 'manual': 'Use the menu to refresh',
        'refresh': 'Refresh now', 'language': 'Language / 语言',
        'quit': 'Quit', 'loading': 'Loading…', 'short': 'Short term', 'long': 'Long term',
    },
}


def percentage(window):
    value = (window or {}).get('usedPercent')
    return '—' if value is None else f'{max(0, min(100, float(value))):g}%'


def window_name(window, fallback, language):
    minutes = (window or {}).get('windowDurationMins')
    if minutes == 10080:
        return TEXT[language]['week']
    if minutes and minutes % 60 == 0:
        return f'{minutes // 60}h'
    return f'{minutes}m' if minutes else fallback


def reset_text(window, language):
    stamp = (window or {}).get('resetsAt')
    if not stamp:
        return TEXT[language]['unknown']
    return dt.datetime.fromtimestamp(stamp).strftime('%m-%d %H:%M')


class Indicator:
    def __init__(self):
        self.busy = False
        self.last = None
        self.last_time = None
        self.last_error = None
        self.language = self.load_language()
        self.client = UsageClient(self.on_rate_limits_updated)
        self.lib = ctypes.CDLL(ctypes.util.find_library('ayatana-appindicator3'))
        self.configure_library()
        self.handle = self.lib.app_indicator_new(
            b'codex-usage-topbar', b'utilities-system-monitor-symbolic', 0)
        self.lib.app_indicator_set_status(self.handle, 1)
        self.create_menu()
        self.label('Codex …')
        self.refresh()
        GLib.timeout_add_seconds(1800, self.refresh)

    def configure_library(self):
        signatures = [
            ('app_indicator_new', [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int], ctypes.c_void_p),
            ('app_indicator_set_status', [ctypes.c_void_p, ctypes.c_int], None),
            ('app_indicator_set_label', [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p], None),
            ('app_indicator_set_menu', [ctypes.c_void_p, ctypes.c_void_p], None),
        ]
        for name, arguments, result in signatures:
            function = getattr(self.lib, name)
            function.argtypes, function.restype = arguments, result

    def create_menu(self):
        self.menu = Gtk.Menu()
        self.rows = []
        for _ in range(5):
            row = Gtk.MenuItem(label=TEXT[self.language]['loading'])
            row.set_sensitive(False)
            self.menu.append(row)
            self.rows.append(row)
        self.menu.append(Gtk.SeparatorMenuItem())
        self.refresh_item = Gtk.MenuItem()
        self.refresh_item.connect('activate', lambda *_: self.refresh())
        self.menu.append(self.refresh_item)
        self.language_item = Gtk.MenuItem()
        language_menu = Gtk.Menu()
        for code, label in [('zh', '中文'), ('en', 'English')]:
            item = Gtk.MenuItem(label=label)
            item.connect('activate', self.set_language, code)
            language_menu.append(item)
        language_menu.show_all()
        self.language_item.set_submenu(language_menu)
        self.menu.append(self.language_item)
        self.quit_item = Gtk.MenuItem()
        self.quit_item.connect('activate', lambda *_: Gtk.main_quit())
        self.menu.append(self.quit_item)
        self.refresh_menu_static_text()
        self.menu.show_all()
        capsule_pointer = ctypes.pythonapi.PyCapsule_GetPointer
        capsule_pointer.argtypes = [ctypes.py_object, ctypes.c_char_p]
        capsule_pointer.restype = ctypes.c_void_p
        self.lib.app_indicator_set_menu(
            self.handle, capsule_pointer(self.menu.__gpointer__, None))

    @staticmethod
    def load_language():
        try:
            with open(CONFIG_PATH, encoding='utf-8') as config:
                language = json.load(config).get('language')
                return language if language in TEXT else 'zh'
        except (OSError, ValueError, AttributeError):
            return 'zh'

    def save_language(self):
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, 'w', encoding='utf-8') as config:
                json.dump({'language': self.language}, config)
        except OSError:
            pass

    def set_language(self, _item, language):
        self.language = language
        self.save_language()
        self.refresh_menu_static_text()
        self.render()

    def refresh_menu_static_text(self):
        text = TEXT[self.language]
        self.refresh_item.set_label(text['refresh'])
        self.language_item.set_label(text['language'])
        self.quit_item.set_label(text['quit'])

    def label(self, text):
        self.lib.app_indicator_set_label(
            self.handle, text.encode(), b'Codex 5h 100% | W 100%')

    def refresh(self):
        if not self.busy:
            self.busy = True
            threading.Thread(target=self.fetch, daemon=True).start()
        return GLib.SOURCE_CONTINUE

    def fetch(self):
        try:
            result = self.client.connect() if not self.client.connected else self.client.read_limits()
            error = None
        except Exception as exception:
            result, error = None, str(exception)
        GLib.idle_add(self.update, result, error)

    def on_rate_limits_updated(self, limits):
        if limits:
            GLib.idle_add(self.update_from_notification, limits)

    def update_from_notification(self, limits):
        self.last = {**(self.last or {}), **limits}
        self.last_time = dt.datetime.now()
        self.last_error = None
        self.render()
        return GLib.SOURCE_REMOVE

    def update(self, result, error):
        self.busy = False
        if result:
            self.last, self.last_time = result, dt.datetime.now()
        self.last_error = error
        self.render()
        return GLib.SOURCE_REMOVE

    def render(self):
        text = TEXT[self.language]
        if self.last:
            primary, secondary = self.last.get('primary'), self.last.get('secondary')
            label = (
                f'Codex {window_name(primary, "5h", self.language)} {percentage(primary)} | '
                f'{window_name(secondary, text["week"], self.language)} {percentage(secondary)}'
            )
            self.label(label + (' ⚠' if self.last_error else ''))
            labels = [
                f'Codex · {(self.last.get("planType") or text["subscription"]).title()} · {text["used"]}',
                f'{window_name(primary, text["short"], self.language)}: {text["used"]} {percentage(primary)} · {text["reset"]} {reset_text(primary, self.language)}',
                f'{window_name(secondary, text["long"], self.language)}: {text["used"]} {percentage(secondary)} · {text["reset"]} {reset_text(secondary, self.language)}',
                f'{text["updated"]} {self.last_time:%H:%M:%S} · {text["every_minute"]}',
                text['stale'] + self.last_error if self.last_error else text['local_time'],
            ]
        else:
            self.label('Codex ⚠')
            labels = [
                text['unavailable'], self.last_error or text['waiting'], text['login'],
                text['retry'], text['manual'],
            ]
        for row, label in zip(self.rows, labels):
            row.set_label(label)


if __name__ == '__main__':
    lock_path = os.path.join(
        os.environ.get('XDG_RUNTIME_DIR', '/tmp'), f'codex-usage-{os.getuid()}.lock')
    lock = open(lock_path, 'w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit(0)
    indicator = Indicator()

    def shutdown(*_):
        indicator.client.close()
        Gtk.main_quit()

    signal.signal(signal.SIGTERM, shutdown)
    Gtk.main()
