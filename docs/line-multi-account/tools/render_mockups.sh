#!/usr/bin/env bash
# 用无头 Chrome 把 tools/mockups/*.html 渲染成 images/*.png（2 倍图）。
# 用法: bash docs/line-multi-account/tools/render_mockups.sh
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$(cd "$DIR/.." && pwd)/images"
CHROME="${CHROME:-$(command -v google-chrome || command -v chromium || command -v chromium-browser)}"
mkdir -p "$OUT"

render() { # $1=html 文件名  $2=输出名  $3=窗口宽  $4=窗口高
  local profile
  profile="$(mktemp -d /tmp/chrome-linehub-XXXXXX)"
  # Chrome 写完截图后常常不退出，用 timeout 收尸；文件写出来就算成功。
  timeout 25 "$CHROME" --headless=new --disable-gpu --no-sandbox --hide-scrollbars \
    --disable-dev-shm-usage --no-first-run --no-default-browser-check \
    --user-data-dir="$profile" --remote-debugging-port=0 \
    --virtual-time-budget=5000 \
    --force-device-scale-factor=2 --window-size="$3,$4" \
    --screenshot="$OUT/$2" "file://$DIR/mockups/$1" || true
  rm -rf "$profile"
  if [[ ! -s "$OUT/$2" ]]; then
    echo "failed to write images/$2" >&2
    exit 1
  fi
  echo "wrote images/$2"
}

render 02-oa-enable-messaging-api.html 02-oa-enable-messaging-api.png 1100 560
render 05-basic-settings.html          05-basic-settings-secret.png   1100 620
render 06-messaging-api-token.html     06-messaging-api-token.png     1100 780
render 10-architecture.html            10-architecture.png            1200 720
render 11-deploy-topology.html         11-deploy-topology.png         1200 620
render 13-key-table.html               13-key-table.png               1180 480
