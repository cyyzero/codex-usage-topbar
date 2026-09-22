# Codex Usage Topbar

[English README](README.md)

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
git clone <你的仓库地址>
cd codex-usage-topbar
bash install.sh
```

程序会安装到 `~/.local/share/codex-usage-topbar`。安装脚本会创建 `~/.config/autostart/codex-usage-topbar.desktop`，因此下次登录会自动启动；不需要 sudo。

组件会监控本机 ChatGPT/Codex Desktop 进程：只有 Desktop 打开时，顶栏才可见并保持本地 app-server 接收器；Desktop 退出后，顶栏会隐藏并关闭该接收器。默认可执行文件路径为 `/usr/lib/chatgpt/ChatGPT`；若安装位置不同，可在启动前设置 `CODEX_DESKTOP_EXECUTABLE`。

## 卸载

先在顶栏菜单选择 **退出 / Quit**，然后执行：

```bash
rm ~/.config/autostart/codex-usage-topbar.desktop
rm -r ~/.local/share/codex-usage-topbar
```

## 数据来源

组件不会调用 `account/rateLimits/read`。它保持本机 app-server 连接，只接收 `account/rateLimits/updated` 的变更推送；在 Codex 发出第一次用量变化前，顶栏会显示等待状态。详情请见 [Codex App Server documentation](https://learn.chatgpt.com/docs/app-server)。
