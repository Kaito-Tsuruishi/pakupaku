"""録音開始/停止音と osascript 通知"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from pakupaku.config import (
    FALLBACK_START_SOUND,
    FALLBACK_STOP_SOUND,
    START_SOUND_PATH,
    STOP_SOUND_PATH,
)


def _find_hs_cli() -> str | None:
    """Hammerspoon の hs CLI の絶対パスを返す。見つからなければ None。

    launchd 配下の daemon は PATH が制限されているため、Homebrew のパスを
    明示的に探しに行く必要がある。
    """
    found = shutil.which("hs")
    if found is not None:
        return found
    for candidate in ("/opt/homebrew/bin/hs", "/usr/local/bin/hs"):
        if Path(candidate).exists():
            return candidate
    return None


_HS_CLI: str | None = _find_hs_cli()


def _play(path: str) -> None:
    """afplay で短いシステム音を非同期再生"""
    try:
        subprocess.Popen(
            ["afplay", path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        pass


def play_start_sound() -> None:
    """録音開始音"""
    path = str(START_SOUND_PATH) if START_SOUND_PATH.exists() else FALLBACK_START_SOUND
    _play(path)


def play_stop_sound() -> None:
    """録音停止音"""
    path = str(STOP_SOUND_PATH) if STOP_SOUND_PATH.exists() else FALLBACK_STOP_SOUND
    _play(path)


def notify(message: str, title: str = "pakupaku") -> None:
    """macOS の通知バナーを表示する"""
    try:
        # AppleScript の文字列にメッセージを安全に埋め込む
        safe_message = message.replace('"', '\\"')
        safe_title = title.replace('"', '\\"')
        subprocess.run(
            [
                "osascript",
                "-e",
                f'display notification "{safe_message}" with title "{safe_title}"',
            ],
            capture_output=True,
            timeout=3,
        )
    except Exception:
        pass


def show_status(message: str | None) -> None:
    """画面下端に進捗を表示する (Hammerspoon hs.alert 経由、置き換え式)

    Hammerspoon が起動していない場合や hs CLI が見つからない場合は静かに失敗する
    (daemon の動作には影響しない)。

    Args:
        message: 表示する文字列。None または空文字列なら現在の表示を消す。
    """
    if _HS_CLI is None:
        return
    msg = message if message is not None else ""
    safe_msg = msg.replace("\\", "\\\\").replace('"', '\\"')
    try:
        subprocess.run(
            [_HS_CLI, "-c", f'pakupakuStatus("{safe_msg}")'],
            capture_output=True,
            timeout=2,
        )
    except Exception:
        pass
