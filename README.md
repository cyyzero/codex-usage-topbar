# Codex Usage Topbar

[中文说明](README.zh-CN.md)

Show current Codex subscription usage in the Ubuntu GNOME top panel. It uses the locally signed-in Codex account and never reads or stores sign-in tokens.

![Ubuntu GNOME top-panel indicator and language menu](docs/topbar-demo.png)

The panel shows a compact label such as `Codex 5h 13% | W 7%`. Percentages are usage consumed. Open the indicator to see local reset times and refresh on demand.

Choose **Language / 语言** in the menu to switch between English and Chinese. The selection is saved in `~/.config/codex-usage-topbar/config.json` and restored on the next launch.

## Requirements

- Ubuntu GNOME with the Ubuntu AppIndicators extension enabled
- Python 3, PyGObject / GTK 3, and libayatana-appindicator3
- A signed-in Codex CLI or Codex desktop app

## Install

```bash
git clone <your-repository-url>
cd codex-usage-topbar
bash install.sh
```

The app is installed in `~/.local/share/codex-usage-topbar`. The installer creates `~/.config/autostart/codex-usage-topbar.desktop`, so it starts at the next login. No sudo is required.

## Uninstall

Choose **Quit / 退出** in the panel menu, then run:

```bash
rm ~/.config/autostart/codex-usage-topbar.desktop
rm -r ~/.local/share/codex-usage-topbar
```

## Data source

The indicator refreshes every 60 seconds through the Codex app-server `account/rateLimits/read` method. See the [Codex App Server documentation](https://learn.chatgpt.com/docs/app-server).
