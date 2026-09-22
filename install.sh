#!/bin/bash
set -euo pipefail

source_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
install_dir="$HOME/.local/share/codex-usage-topbar"
autostart_dir="$HOME/.config/autostart"

mkdir -p "$install_dir" "$autostart_dir"
install -m 644 "$source_dir/usage.py" "$source_dir/indicator.py" "$install_dir/"

desktop_file="$autostart_dir/codex-usage-topbar.desktop"
printf '%s\n' \
  '[Desktop Entry]' \
  'Type=Application' \
  'Name=Codex Usage' \
  'Comment=Show Codex subscription usage in the Ubuntu top panel' \
  "Exec=/usr/bin/python3 $install_dir/indicator.py" \
  'Icon=utilities-system-monitor' \
  'Terminal=false' \
  'X-GNOME-Autostart-enabled=true' > "$desktop_file"

nohup /usr/bin/python3 "$install_dir/indicator.py" \
  > "$install_dir/indicator.log" 2>&1 < /dev/null &

echo 'Installed. The indicator will also start automatically after the next login.'
