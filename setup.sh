#!/usr/bin/env bash
# pakupaku セットアップスクリプト
#
# 使い方:
#   1. このリポジトリを clone (例: git clone <URL> ~/pakupaku)
#   2. cd ~/pakupaku
#   3. bash setup.sh
#
# このスクリプトの動作:
#   1. 前提ツール (Homebrew, uv) を確認・なければインストール案内
#   2. Homebrew パッケージ (hammerspoon, ffmpeg) をインストール
#   3. uv で Python 依存をインストール (uv sync)
#   4. GiNZA 互換パッチを適用
#   5. Hammerspoon 設定 (~/.hammerspoon/pakupaku.lua) を配置
#   6. launchd plist を登録 (pakupaku daemon を自動起動)
#   7. 権限取得の手引きを表示
#
# Idempotent: 何度実行しても同じ結果になるよう設計。
# 失敗時は途中で止まり、原因を表示。

set -euo pipefail

# ==================
# 共通定義
# ==================

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${PROJECT_DIR}"

# カラー出力
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
RESET='\033[0m'

ok()    { printf "${GREEN}✓${RESET} %s\n" "$*"; }
warn()  { printf "${YELLOW}!${RESET} %s\n" "$*"; }
error() { printf "${RED}✗${RESET} %s\n" "$*"; }
info()  { printf "${BLUE}>${RESET} %s\n" "$*"; }
step()  { printf "\n${BLUE}===== %s =====${RESET}\n" "$*"; }

# ==================
# 前提チェック
# ==================

step "前提条件のチェック"

# macOS チェック
if [[ "$(uname)" != "Darwin" ]]; then
    error "macOS でのみ動作します (現在: $(uname))"
    exit 1
fi
ok "macOS $(sw_vers -productVersion)"

# Apple Silicon チェック
if [[ "$(uname -m)" != "arm64" ]]; then
    warn "Apple Silicon 以外では動作しません (現在: $(uname -m))"
    warn "Whisper / SLM の MLX 推論は動きません"
fi

# ==================
# Homebrew
# ==================

step "Homebrew のチェック"

if ! command -v brew >/dev/null 2>&1; then
    error "Homebrew がインストールされていません"
    echo ""
    echo "以下を実行して Homebrew をインストールしてから再実行してください:"
    echo ""
    echo '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
    echo ""
    exit 1
fi
ok "Homebrew $(brew --version | head -1 | awk '{print $2}')"

# ==================
# uv
# ==================

step "uv のチェック"

UV_PATH="${HOME}/.local/bin/uv"
if ! command -v uv >/dev/null 2>&1 && [[ ! -x "${UV_PATH}" ]]; then
    info "uv をインストールします..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    if [[ ! -x "${UV_PATH}" ]]; then
        error "uv のインストールに失敗しました"
        exit 1
    fi
fi

if command -v uv >/dev/null 2>&1; then
    UV="uv"
else
    UV="${UV_PATH}"
fi
ok "uv $(${UV} --version | awk '{print $2}')"

# ==================
# Homebrew パッケージ
# ==================

step "Homebrew パッケージ"

# Hammerspoon
if [[ -d "/Applications/Hammerspoon.app" ]]; then
    ok "Hammerspoon (インストール済み)"
else
    info "Hammerspoon をインストールします..."
    brew install --cask hammerspoon
    ok "Hammerspoon インストール完了"
fi

# ffmpeg
if command -v ffmpeg >/dev/null 2>&1; then
    ok "ffmpeg (インストール済み)"
else
    info "ffmpeg をインストールします..."
    brew install ffmpeg
    ok "ffmpeg インストール完了"
fi

# ==================
# Python 環境
# ==================

step "Python 環境"

# Python 3.12 が uv で利用可能か
if ! ${UV} python list 2>/dev/null | grep -q "3\.12"; then
    info "Python 3.12 をインストールします..."
    ${UV} python install 3.12
fi
ok "Python 3.12 利用可能"

info "依存パッケージをインストールします (時間がかかる場合あり)..."
${UV} sync
ok "依存パッケージ install 完了"

info "GiNZA 互換パッチを適用します..."
${UV} run python scripts/patch_ginza.py
ok "GiNZA パッチ完了"

# ==================
# Hammerspoon 設定
# ==================

step "Hammerspoon 設定"

mkdir -p "${HOME}/.hammerspoon"

# pakupaku.lua をコピー
cp "${PROJECT_DIR}/scripts/hammerspoon/pakupaku.lua" "${HOME}/.hammerspoon/pakupaku.lua"
ok "~/.hammerspoon/pakupaku.lua をコピー"

# init.lua に require を追加 (重複防止)
INIT_LUA="${HOME}/.hammerspoon/init.lua"
if [[ ! -f "${INIT_LUA}" ]]; then
    echo 'require("pakupaku")' > "${INIT_LUA}"
    ok "~/.hammerspoon/init.lua を作成"
elif ! grep -q 'require("pakupaku")' "${INIT_LUA}"; then
    echo 'require("pakupaku")' >> "${INIT_LUA}"
    ok "~/.hammerspoon/init.lua に require を追加"
else
    ok "~/.hammerspoon/init.lua は既に設定済み"
fi

# ==================
# launchd 登録
# ==================

step "launchd デーモン登録"

# install_launchd.sh はサブコマンド扱い
bash "${PROJECT_DIR}/scripts/install_launchd.sh" >/dev/null
ok "pakupaku daemon を launchd に登録"

# ==================
# shell alias (paku コマンド)
# ==================

step "shell alias (paku) の設定"

ZSHRC="${HOME}/.zshrc"
PAKU_BIN="${PROJECT_DIR}/.venv/bin/paku"
MARK_BEGIN="# >>> pakupaku >>>"
MARK_END="# <<< pakupaku <<<"

# .zshrc が無ければ作成
if [[ ! -f "${ZSHRC}" ]]; then
    touch "${ZSHRC}"
    ok "~/.zshrc を作成"
fi

# マーカー外の旧来手書き alias 行を削除 (重複・順序負けを防ぐ)
if grep -E '^[[:space:]]*alias[[:space:]]+paku=' "${ZSHRC}" >/dev/null 2>&1; then
    # マーカーブロック内の行はいったん保護してから削除し、最後に書き戻す
    TMP_ZSHRC="$(mktemp)"
    awk -v b="${MARK_BEGIN}" -v e="${MARK_END}" '
        $0 == b { in_block = 1 }
        in_block { print; if ($0 == e) in_block = 0; next }
        /^[[:space:]]*alias[[:space:]]+paku=/ { next }
        { print }
    ' "${ZSHRC}" > "${TMP_ZSHRC}"
    mv "${TMP_ZSHRC}" "${ZSHRC}"
fi

# マーカーブロックがあれば中身を差し替え、無ければ末尾に追記
if grep -qF "${MARK_BEGIN}" "${ZSHRC}" 2>/dev/null; then
    TMP_ZSHRC="$(mktemp)"
    awk -v b="${MARK_BEGIN}" -v e="${MARK_END}" -v bin="${PAKU_BIN}" '
        $0 == b {
            print b
            print "alias paku=\"" bin "\""
            print e
            in_block = 1
            next
        }
        in_block {
            if ($0 == e) in_block = 0
            next
        }
        { print }
    ' "${ZSHRC}" > "${TMP_ZSHRC}"
    mv "${TMP_ZSHRC}" "${ZSHRC}"
    ok "~/.zshrc の alias を更新"
else
    # 末尾に改行が無ければ補ってから追記
    if [[ -s "${ZSHRC}" ]] && [[ "$(tail -c 1 "${ZSHRC}" | xxd -p)" != "0a" ]]; then
        printf "\n" >> "${ZSHRC}"
    fi
    {
        printf "\n%s\n" "${MARK_BEGIN}"
        printf 'alias paku="%s"\n' "${PAKU_BIN}"
        printf "%s\n" "${MARK_END}"
    } >> "${ZSHRC}"
    ok "~/.zshrc に alias を追加"
fi

# ==================
# 完了案内
# ==================

step "セットアップ完了"

cat <<'EOF'

⚠️  daemon が起動し、バックグラウンドで初回モデルダウンロード (約 5GB)
    が始まっています。回線にもよりますが 5〜15 分程度かかります。
    完了は `paku status` の SLM 行で確認できます (ロード完了で `✓ loaded`)。

ℹ️  `paku` コマンドを使うには、新しいターミナルを開くか以下を実行してください:

    source ~/.zshrc

次の手順:

  1. macOS 権限の取得 (5〜10 分の GUI 操作)

     bash scripts/open_permissions.sh

     - マイク権限は次回録音時にダイアログで許可
     - アクセシビリティ: Python と Hammerspoon を追加してオン
     - 入力監視: Hammerspoon を追加してオン

  2. 権限取得の確認

     uv run python scripts/check_permissions.py

  3. Hammerspoon を起動 (まだなら) + 自動起動を設定

     - Spotlight で "Hammerspoon" 検索 → 起動
     - メニューバー → Preferences → General で
       "Launch Hammerspoon at login" にチェック
     - メニューバーアイコンから "Reload Config" をクリック
     - 「pakupaku: hotkey loaded」と表示されれば OK

  4. モデル DL の完了を待つ

     paku status

     SLM 行が `✓ loaded (...)` になったら次へ。
     `○ not loaded` のままなら DL 中なのでもうしばらく待つ。

  5. 動作テスト

     - 任意のテキストエディタを開く
     - ⌃⇧Space (Ctrl + Shift + Space) を押す → 録音開始音
     - 「えーと、明日の会議に参加します」と話す
     - ⌃⇧Space をもう一度押す → 録音停止音
     - 数秒後、エディタに「明日の会議に参加します。」が貼り付く

困ったときは:

  - 動作状態の確認:    paku status
  - daemon ログ:       tail -f ~/Library/Logs/pakupaku/daemon.log
  - daemon 再起動:     paku restart
  - 完全アンインストール: bash uninstall.sh

  - 権限が突然外れた場合 (Sonoma 以降の不具合):
      tccutil reset Accessibility
      tccutil reset Microphone
      tccutil reset ListenEvent
    その後、もう一度 bash scripts/open_permissions.sh を実行

EOF
