# Codex Usage Topbar

[English README](README.md)

源码仓库：[cyyzero/codex-usage-topbar](https://github.com/cyyzero/codex-usage-topbar)

在 Ubuntu GNOME 顶栏显示当前 Codex 订阅额度。顶栏程序只通过标准输入输出与本机 `codex app-server` 通信，由 Codex 自己处理到 OpenAI 的认证连接；顶栏不会读取或保存登录令牌。

![Ubuntu GNOME 顶栏指示器和语言切换菜单](docs/topbar-demo.png)

顶栏会显示类似 `Codex 5h 13% | 周 7%` 的文字；百分比表示已用额度。点击指示器可查看本地重置时间，并随时手动刷新。

通过菜单中的 **语言 / Language** 可切换中文和 English。选择会保存到 `~/.config/codex-usage-topbar/config.json`，下次启动时自动恢复。

## 运行环境

- 已启用 Ubuntu AppIndicators 扩展的 Ubuntu GNOME
- Python 3、PyGObject / GTK 3、libayatana-appindicator3
- 已登录的 Codex CLI 或 Codex desktop app

## 安装

```bash
git clone https://github.com/cyyzero/codex-usage-topbar.git
cd codex-usage-topbar
bash install.sh
```

程序会安装到 `~/.local/share/codex-usage-topbar`。安装脚本会创建 `~/.config/autostart/codex-usage-topbar.desktop`，因此下次登录会自动启动；不需要 sudo。

组件通过会话 D-Bus 监听 GNOME 的 StatusNotifierWatcher，并用 `ChatGPT` 提示文本识别 Desktop 的状态项：只有 Desktop 打开时，顶栏才可见并保持本地 app-server 接收器；Desktop 退出后，顶栏会隐藏并关闭该接收器。该方式不会扫描 `/proc`。

GNOME 锁屏时可能会临时撤销 Desktop 的状态项。组件会在锁屏期间保留当前状态，并在解锁时重新检查 Desktop，因此解锁后会恢复到顶栏。

## 卸载

先在顶栏菜单选择 **退出 / Quit**，然后执行：

```bash
rm ~/.config/autostart/codex-usage-topbar.desktop
rm -r ~/.local/share/codex-usage-topbar
```

## 数据来源

Desktop 启动顶栏时、你选择 **立即刷新** 时，以及 Desktop 打开期间每分钟一次，组件会通过本机 Codex 的 `account/rateLimits/read` 读取当前快照；同时保持本机 app-server 连接，接收到达的 `account/rateLimits/updated` 推送。定期的本机校验可避免漏掉推送后顶栏长期展示过期数据。详情请见 [Codex App Server documentation](https://learn.chatgpt.com/docs/app-server)。
