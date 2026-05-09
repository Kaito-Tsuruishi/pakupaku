#!/usr/bin/env bash
# pakupaku に必要な macOS 権限設定画面を順に開くスクリプト
#
# 使い方: bash scripts/open_permissions.sh

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON_LINK="${PROJECT_DIR}/.venv/bin/python"
# venv の python はシンボリックリンクなので実体パスも取得
VENV_PYTHON_REAL="$(/usr/bin/readlink -f "${VENV_PYTHON_LINK}" 2>/dev/null || echo "${VENV_PYTHON_LINK}")"

echo "===================="
echo "pakupaku 権限セットアップ"
echo "===================="
echo ""
echo "Python の実体パス (これを各権限画面に追加):"
echo "  ${VENV_PYTHON_REAL}"
echo ""
echo "venv のリンク (こちらでも可、両方追加が安全):"
echo "  ${VENV_PYTHON_LINK}"
echo ""
echo "コピー用にクリップボードへ実体パスを貼り付けます:"
echo -n "${VENV_PYTHON_REAL}" | pbcopy
echo "  → クリップボードにコピーされました"
echo "  → 各権限画面で [+] → ⌘+⇧+G → ペースト → 選択 でトグルが追加されます"
echo ""

read -p "Enter キーで「マイク」設定を開きます..." _
open "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"
echo "  → リストで Python が表示されたらトグルをオン"
echo "  → 表示されない場合は [+] ボタンで追加 (⌘+⇧+G で上記パス貼り付け)"
echo ""

read -p "Enter キーで「アクセシビリティ」設定を開きます..." _
open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
echo "  → Hammerspoon と Python を [+] ボタンで追加 (両方トグルをオン)"
echo "  → Hammerspoon は /Applications/Hammerspoon.app"
echo "  → Python は ⌘+⇧+G で上記パス貼り付け"
echo ""

read -p "Enter キーで「入力監視」設定を開きます..." _
open "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"
echo "  → Hammerspoon を [+] ボタンで追加"
echo "  → Hammerspoon は /Applications/Hammerspoon.app"
echo ""

echo "===================="
echo "設定完了の確認"
echo "===================="
echo ""
echo "以下を確認してください:"
echo "  [ ] マイク: Python が ON"
echo "  [ ] アクセシビリティ: Hammerspoon と Python が ON"
echo "  [ ] 入力監視: Hammerspoon が ON"
echo ""
echo "全て OK なら次のステップ:"
echo "  uv run python scripts/check_permissions.py   # 権限の自動チェック"
echo "  paku status                                  # daemon の動作確認"
echo "  Hammerspoon Reload Config 後に Ctrl+Shift+Space でテスト"
