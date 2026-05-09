#!/usr/bin/env bash
# pakupaku daemon を launchd に登録するスクリプト
#
# 使い方:
#   bash scripts/install_launchd.sh
#
# 事前条件:
#   - uv sync でプロジェクトの venv が作成済み (.venv/)
#   - HANDOFF.md / README.md の権限手順を済ませた

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="${PROJECT_DIR}/.venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/pakupaku"
PLIST_TEMPLATE="${PROJECT_DIR}/scripts/com.pakupaku.daemon.plist"
LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
TARGET_PLIST="${LAUNCH_AGENTS_DIR}/com.pakupaku.daemon.plist"

if [[ ! -f "${VENV_PYTHON}" ]]; then
    echo "Error: venv Python not found at ${VENV_PYTHON}"
    echo "  Run 'uv sync' first to create the virtual environment."
    exit 1
fi

mkdir -p "${LOG_DIR}"
mkdir -p "${LAUNCH_AGENTS_DIR}"

# プレースホルダーを置換して plist を生成
sed \
    -e "s|__PAKUPAKU_VENV_PYTHON__|${VENV_PYTHON}|g" \
    -e "s|__PAKUPAKU_PROJECT_DIR__|${PROJECT_DIR}|g" \
    -e "s|__PAKUPAKU_LOG_DIR__|${LOG_DIR}|g" \
    "${PLIST_TEMPLATE}" > "${TARGET_PLIST}"
chmod 600 "${TARGET_PLIST}"

# 既存登録があれば一旦アンロード (エラー無視)
launchctl unload "${TARGET_PLIST}" 2>/dev/null || true

# 登録
launchctl load -w "${TARGET_PLIST}"

echo "Installed: ${TARGET_PLIST}"
echo "Log dir: ${LOG_DIR}"
echo ""
echo "Next steps:"
echo "  1. Copy scripts/hammerspoon/pakupaku.lua to ~/.hammerspoon/pakupaku.lua"
echo "  2. Add 'require(\"pakupaku\")' to ~/.hammerspoon/init.lua"
echo "  3. Reload Hammerspoon config"
echo "  4. Grant Accessibility / Microphone / Input Monitoring permissions"
echo "     (System Settings > Privacy & Security)"
