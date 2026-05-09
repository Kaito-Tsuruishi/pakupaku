"""録音開始/停止音と osascript 通知"""

from __future__ import annotations

import subprocess

from pakupaku.config import (
    FALLBACK_START_SOUND,
    FALLBACK_STOP_SOUND,
    START_SOUND_PATH,
    STOP_SOUND_PATH,
)


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
