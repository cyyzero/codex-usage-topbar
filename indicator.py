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
from gi.repository import Gio, GLib, Gtk

from usage import UsageClient


CONFIG_PATH = os.path.join(
    os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config')),
    'codex-usage-topbar',
    'config.json',
)
STATUS_NOTIFIER_WATCHER = 'org.kde.StatusNotifierWatcher'
DESKTOP_STATUS_TOOLTIP = os.environ.get('CODEX_DESKTOP_STATUS_TOOLTIP', 'ChatGPT')
SCREEN_SAVER_SERVICE = 'org.gnome.ScreenSaver'
SCREEN_SAVER_PATH = '/org/gnome/ScreenSaver'

TEXT = {
    'zh': {
        'week': '周', 'unknown': '未知', 'subscription': '订阅',
        'used': '已用', 'reset': '重置', 'updated': '上次更新',
        'every_minute': '实时推送；启动和手动刷新时读取', 'local_time': '重置时间为本地时间',
        'stale': '⚠ 数据可能过期：', 'unavailable': 'Codex · 暂时无法读取',
        'waiting': '等待数据', 'login': '请确认 Codex 已登录',
        'retry': '请检查本机 Codex 状态后刷新', 'manual': '菜单可手动刷新',
        'refresh': '立即刷新', 'language': '语言 / Language',
        'quit': '退出', 'loading': '正在读取…', 'short': '短期', 'long': '长期',
    },
    'en': {
        'week': 'W', 'unknown': 'Unknown', 'subscription': 'Subscription',
        'used': 'Used', 'reset': 'Resets', 'updated': 'Last updated',
        'every_minute': 'Live updates; reads on start and manual refresh', 'local_time': 'Reset times are local',
        'stale': '⚠ Data may be stale: ', 'unavailable': 'Codex · unavailable',
        'waiting': 'Waiting for data', 'login': 'Make sure Codex is signed in',
        'retry': 'Check local Codex and refresh', 'manual': 'Use the menu to refresh',
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


def desktop_app_running(session_bus):
    """Detect the Desktop app through its GNOME status-notifier registration."""
    if not session_bus:
        return False
    try:
        items = session_bus.call_sync(
            STATUS_NOTIFIER_WATCHER, '/StatusNotifierWatcher',
            'org.freedesktop.DBus.Properties', 'Get',
            GLib.Variant('(ss)', (STATUS_NOTIFIER_WATCHER, 'RegisteredStatusNotifierItems')),
            GLib.VariantType('(v)'), Gio.DBusCallFlags.NONE, 1000, None).unpack()[0]
        for item in items:
            service, path = item.split('@', 1) if '@' in item else (item, '/StatusNotifierItem')
            try:
                tooltip = session_bus.call_sync(
                    service, path, 'org.freedesktop.DBus.Properties', 'Get',
                    GLib.Variant('(ss)', ('org.kde.StatusNotifierItem', 'ToolTip')),
                    GLib.VariantType('(v)'), Gio.DBusCallFlags.NONE, 500, None).unpack()[0]
            except GLib.Error:
                continue
            if len(tooltip) > 2 and tooltip[2] == DESKTOP_STATUS_TOOLTIP:
                return True
    except GLib.Error:
        return False
    return False


def screen_locked(session_bus):
    if not session_bus:
        return False
    try:
        return session_bus.call_sync(
            SCREEN_SAVER_SERVICE, SCREEN_SAVER_PATH,
            SCREEN_SAVER_SERVICE, 'GetActive', None,
            GLib.VariantType('(b)'), Gio.DBusCallFlags.NONE, 1000, None).unpack()[0]
    except GLib.Error:
        return False


class Indicator:
    def __init__(self):
        self.busy = False
        self.last = None
        self.last_time = None
        self.last_error = None
        self.connection_ready = False
        self.desktop_running = False
        self.screen_locked = False
        self.lifecycle_generation = 0
        try:
            self.session_bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            self.status_notifier_subscription = self.session_bus.signal_subscribe(
                STATUS_NOTIFIER_WATCHER, 'org.kde.StatusNotifierWatcher', None,
                '/StatusNotifierWatcher', None, Gio.DBusSignalFlags.NONE,
                self.on_status_notifier_signal, None)
            self.screen_saver_subscription = self.session_bus.signal_subscribe(
                SCREEN_SAVER_SERVICE, SCREEN_SAVER_SERVICE, 'ActiveChanged',
                SCREEN_SAVER_PATH, None, Gio.DBusSignalFlags.NONE,
                self.on_screen_saver_signal, None)
            self.screen_locked = screen_locked(self.session_bus)
        except GLib.Error:
            self.session_bus = None
            self.status_notifier_subscription = None
            self.screen_saver_subscription = None
        self.language = self.load_language()
        self.client = UsageClient(self.on_rate_limits_updated)
        self.lib = ctypes.CDLL(ctypes.util.find_library('ayatana-appindicator3'))
        self.configure_library()
        self.handle = self.lib.app_indicator_new(
            b'codex-usage-topbar', b'utilities-system-monitor-symbolic', 0)
        self.lib.app_indicator_set_status(self.handle, 0)
        self.create_menu()
        self.label('Codex …')
        self.sync_desktop_lifecycle()

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
                return language if language in TEXT else 'en'
        except (OSError, ValueError, AttributeError):
            return 'en'

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
        if self.desktop_running and not self.busy:
            self.busy = True
            generation = self.lifecycle_generation
            threading.Thread(target=self.fetch, args=(generation,), daemon=True).start()

    def fetch(self, generation):
        if generation != self.lifecycle_generation or not self.desktop_running:
            return
        try:
            self.client.connect()
            result = self.client.read_limits()
            error = None
        except Exception as exception:
            result, error = None, str(exception)
        GLib.idle_add(self.update, generation, result, error)

    def sync_desktop_lifecycle(self):
        running = desktop_app_running(self.session_bus)
        # GNOME may withdraw Desktop's status item while the screen is locked.
        # Preserve an already-visible indicator until the unlock check confirms exit.
        if self.screen_locked and self.desktop_running and not running:
            return GLib.SOURCE_CONTINUE
        if running == self.desktop_running:
            return GLib.SOURCE_CONTINUE
        self.desktop_running = running
        self.lifecycle_generation += 1
        if running:
            self.lib.app_indicator_set_status(self.handle, 1)
            self.refresh()
        else:
            self.client.close()
            self.busy = False
            self.connection_ready = False
            self.last = None
            self.last_time = None
            self.last_error = None
            self.lib.app_indicator_set_status(self.handle, 0)
        return GLib.SOURCE_CONTINUE

    def on_status_notifier_signal(self, _connection, _sender, _path, _interface,
                                  signal, _parameters, _user_data):
        if signal in ('StatusNotifierItemRegistered', 'StatusNotifierItemUnregistered'):
            self.sync_desktop_lifecycle()

    def on_screen_saver_signal(self, _connection, _sender, _path, _interface,
                                _signal, parameters, _user_data):
        self.screen_locked = parameters.unpack()[0]
        if not self.screen_locked:
            self.sync_desktop_lifecycle()

    def on_rate_limits_updated(self, limits):
        if limits and self.desktop_running:
            GLib.idle_add(self.update_from_notification, limits)

    def update_from_notification(self, limits):
        self.last = {**(self.last or {}), **limits}
        self.last_time = dt.datetime.now()
        self.last_error = None
        self.connection_ready = True
        self.render()
        return GLib.SOURCE_REMOVE

    def update(self, generation, result, error):
        if generation != self.lifecycle_generation or not self.desktop_running:
            return GLib.SOURCE_REMOVE
        self.busy = False
        self.connection_ready = error is None
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
            self.label('Codex …' if self.connection_ready else 'Codex ⚠')
            if self.connection_ready:
                labels = [
                    f'Codex · {text["waiting"]}', text['manual'], text['every_minute'],
                    text['local_time'], text['refresh'],
                ]
            else:
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
