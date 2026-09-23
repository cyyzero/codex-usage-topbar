# Codex Usage Topbar

[中文说明](README.zh-CN.md)

Source: [cyyzero/codex-usage-topbar](https://github.com/cyyzero/codex-usage-topbar)

Show current Codex subscription usage in the Ubuntu GNOME top panel. The indicator talks only to the local `codex app-server` process over standard input/output; Codex handles its own authenticated connection to OpenAI. The indicator never reads or stores sign-in tokens.

![Ubuntu GNOME top-panel indicator and language menu](docs/topbar-demo.png)

The panel shows a compact label such as `Codex 5h 13% | W 7%`. Percentages are usage consumed. Open the indicator to see local reset times and refresh on demand.

Choose **Language / 语言** in the menu to switch between English and Chinese. The selection is saved in `~/.config/codex-usage-topbar/config.json` and restored on the next launch.

## Requirements

- Ubuntu GNOME with the Ubuntu AppIndicators extension enabled
- Python 3, PyGObject / GTK 3, and libayatana-appindicator3
- A signed-in Codex CLI or Codex desktop app

## Install

```bash
git clone https://github.com/cyyzero/codex-usage-topbar.git
cd codex-usage-topbar
bash install.sh
```

The app is installed in `~/.local/share/codex-usage-topbar`. The installer creates `~/.config/autostart/codex-usage-topbar.desktop`, so it starts at the next login. No sudo is required.

The indicator listens to GNOME's StatusNotifierWatcher over the session D-Bus and identifies the Desktop status item with the `ChatGPT` tooltip. It is visible and keeps its local app-server receiver only while Desktop is open; it hides and closes that receiver when Desktop exits. This avoids scanning `/proc`.

GNOME can temporarily withdraw Desktop's status item while the screen is locked. The indicator preserves its current state during the lock and checks Desktop again when you unlock, so it returns to the top panel after unlocking.

## Uninstall

Choose **Quit / 退出** in the panel menu, then run:

```bash
rm ~/.config/autostart/codex-usage-topbar.desktop
rm -r ~/.local/share/codex-usage-topbar
```

## Data source

When Desktop starts the indicator, when you select **Refresh now**, and once per minute while Desktop is open, the indicator asks local Codex for a current snapshot through `account/rateLimits/read`. It also applies `account/rateLimits/updated` notifications when they arrive. The periodic local check prevents a missed notification from leaving stale usage in the panel. See the [Codex App Server documentation](https://learn.chatgpt.com/docs/app-server).
