#!/usr/bin/env bash
# pakupaku アンインストールスクリプト
#
# 使い方: bash uninstall.sh
#
# 削除対象:
#   - launchd 登録 (~/Library/LaunchAgents/com.pakupaku.daemon.plist)
#   - Hammerspoon 設定 (~/.hammerspoon/pakupaku.lua + init.lua の require 行)
#   - モデルキャッシュ (~/.cache/pakupaku/) — オプション
#   - ログ (~/Library/Logs/pakupaku/) — オプション
#
# 削除しないもの (手動で):
#   - pakupaku プロジェクトディレクトリ自体
#   - Homebrew でインストールしたツール (hammerspoon, ffmpeg)
#   - uv 本体
#   - macOS の権限設定

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RESET='\033[0m'

ok()    { printf "${GREEN}✓${RESET} %s\n" "$*"; }
warn()  { printf "${YELLOW}!${RESET} %s\n" "$*"; }
info()  { printf "${BLUE}>${RESET} %s\n" "$*"; }
step()  { printf "\n${BLUE}===== %s =====${RESET}\n" "$*"; }

step "pakupaku アンインストール"

# launchd
PLIST="${HOME}/Library/LaunchAgents/com.pakupaku.daemon.plist"
if [[ -f "${PLIST}" ]]; then
    launchctl unload "${PLIST}" 2>/dev/null || true
    rm -f "${PLIST}"
    ok "launchd 登録を削除"
else
    info "launchd 登録なし (スキップ)"
fi

# Hammerspoon pakupaku.lua
if [[ -f "${HOME}/.hammerspoon/pakupaku.lua" ]]; then
    rm -f "${HOME}/.hammerspoon/pakupaku.lua"
    ok "~/.hammerspoon/pakupaku.lua を削除"
else
    info "~/.hammerspoon/pakupaku.lua なし (スキップ)"
fi

# Hammerspoon init.lua の require 行
INIT_LUA="${HOME}/.hammerspoon/init.lua"
if [[ -f "${INIT_LUA}" ]]; then
    if grep -q 'require("pakupaku")' "${INIT_LUA}"; then
        # require("pakupaku") の行を削除
        sed -i.bak '/require("pakupaku")/d' "${INIT_LUA}"
        rm -f "${INIT_LUA}.bak"
        ok "~/.hammerspoon/init.lua から require 行を削除"
        info "Hammerspoon を再起動するか Reload Config してください"
    fi
fi

# Unix ソケット
if [[ -S "${HOME}/.pakupaku/pakupaku.sock" ]]; then
    rm -f "${HOME}/.pakupaku/pakupaku.sock"
    rmdir "${HOME}/.pakupaku" 2>/dev/null || true
    ok "Unix ソケットを削除"
fi

# ~/.zshrc の alias ブロック
ZSHRC="${HOME}/.zshrc"
MARK_BEGIN="# >>> pakupaku >>>"
MARK_END="# <<< pakupaku <<<"
if [[ -f "${ZSHRC}" ]] && grep -qF "${MARK_BEGIN}" "${ZSHRC}" 2>/dev/null; then
    TMP_ZSHRC="$(mktemp)"
    awk -v b="${MARK_BEGIN}" -v e="${MARK_END}" '
        $0 == b { in_block = 1; next }
        in_block { if ($0 == e) in_block = 0; next }
        { print }
    ' "${ZSHRC}" > "${TMP_ZSHRC}"
    mv "${TMP_ZSHRC}" "${ZSHRC}"
    ok "~/.zshrc から alias ブロックを削除"
fi

# ===== オプション削除 =====

step "オプション削除"

# モデルキャッシュ
if [[ -d "${HOME}/.cache/pakupaku" ]]; then
    SIZE=$(du -sh "${HOME}/.cache/pakupaku" 2>/dev/null | awk '{print $1}')
    read -p "モデルキャッシュ ~/.cache/pakupaku (${SIZE}) を削除しますか? [y/N] " ans
    if [[ "${ans}" =~ ^[Yy]$ ]]; then
        rm -rf "${HOME}/.cache/pakupaku"
        ok "モデルキャッシュを削除"
    else
        info "モデルキャッシュは残します"
    fi
fi

# ログ
if [[ -d "${HOME}/Library/Logs/pakupaku" ]]; then
    read -p "ログ ~/Library/Logs/pakupaku を削除しますか? [y/N] " ans
    if [[ "${ans}" =~ ^[Yy]$ ]]; then
        rm -rf "${HOME}/Library/Logs/pakupaku"
        ok "ログを削除"
    else
        info "ログは残します"
    fi
fi

# ===== 案内 =====

cat <<'EOF'

アンインストール完了。

残っているもの (手動で削除可能):
  - pakupaku プロジェクトディレクトリ (このディレクトリ自体)
  - Homebrew でインストールしたツール:
      brew uninstall --cask hammerspoon
      brew uninstall ffmpeg
  - uv 本体: rm ~/.local/bin/uv
  - macOS の権限設定 (System Settings から手動で削除)
EOF
