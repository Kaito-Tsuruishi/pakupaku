"""クリップボード退避・コピー・⌘V 発火・復元

pyobjc 経由で NSPasteboard を直接扱う。
新しい UTI 識別子 "public.utf8-plain-text" を使用する (Big Sur 以降推奨)。
"""

from __future__ import annotations

import logging
import subprocess
import time

logger = logging.getLogger("pakupaku.clipboard")

# UTI 識別子 (Big Sur 以降の標準)
PASTEBOARD_TYPE_STRING = "public.utf8-plain-text"


def _get_pasteboard():
    """NSPasteboard.generalPasteboard を返す"""
    from AppKit import NSPasteboard

    return NSPasteboard.generalPasteboard()


def get_clipboard() -> tuple[str | None, int]:
    """現在のクリップボード内容を取得 (string, change_count)

    string は文字列が入っている場合のみ。それ以外は None。
    change_count はクリップボードの変更検知用。
    """
    pb = _get_pasteboard()
    change_count = pb.changeCount()
    s = pb.stringForType_(PASTEBOARD_TYPE_STRING)
    return (str(s) if s is not None else None, change_count)


def set_clipboard(text: str) -> None:
    """クリップボードにテキストを書き込む"""
    pb = _get_pasteboard()
    pb.clearContents()
    pb.setString_forType_(text, PASTEBOARD_TYPE_STRING)


def trigger_paste() -> bool:
    """⌘V を発火する (アクセシビリティ権限が必要)

    Returns:
        成功すれば True、失敗 (権限不足等) なら False。
    """
    try:
        result = subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to keystroke "v" using command down',
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def get_frontmost_app() -> str | None:
    """現在フォアグラウンドにあるアプリのバンドル ID を返す。取得失敗時は None。

    バンドル ID で比較する理由は、表示名 (localizedName) はロケール依存だが
    バンドル ID は一意に定まるため。
    """
    try:
        from AppKit import NSWorkspace

        ws = NSWorkspace.sharedWorkspace()
        app = ws.frontmostApplication()
        if app is None:
            return None
        bundle_id = app.bundleIdentifier()
        return str(bundle_id) if bundle_id is not None else None
    except Exception:
        return None


def paste_to_frontmost(
    text: str,
    restore_delay: float = 0.5,
    expected_app: str | None = None,
) -> tuple[bool, str]:
    """テキストをフロントアプリに貼り付ける (退避 → コピー → ⌘V → 復元)

    Args:
        text: 貼り付けるテキスト
        restore_delay: ⌘V 後にクリップボードを復元するまでの待ち時間 (秒)
        expected_app: 録音停止時のフロントアプリのバンドル ID。指定された場合、
                      貼り付け時に同一アプリでないと貼り付けず、テキストはクリップボードに
                      残置する (誤貼り付け事故防止)。None の場合はチェックしない。

    Returns:
        (成功フラグ, 状態文字列) のタプル。失敗時はテキストはクリップボードに残る。
    """
    if not text:
        return False, "empty_text"

    if expected_app is not None:
        current_app = get_frontmost_app()
        logger.info(
            f"Paste app check: expected={expected_app}, current={current_app}"
        )
        if current_app is None:
            # フロントアプリのバンドル ID を取得できない → 安全側に倒して貼り付けない
            # (Fail Closed: 不明な状態で貼り付けて事故るより、クリップボードに残すほうが安全)
            set_clipboard(text)
            return False, "frontmost_app_unknown_text_in_clipboard"
        if current_app != expected_app:
            # フロントアプリが録音停止時から変わっている → 誤貼り付け回避
            set_clipboard(text)
            return False, "frontmost_app_changed_text_in_clipboard"

    original_text, _ = get_clipboard()
    set_clipboard(text)

    # 短い遅延を入れて pasteboard の更新を確実にする
    time.sleep(0.05)

    pasted = trigger_paste()

    if not pasted:
        # 貼り付け失敗 → クリップボードには貼り付けたいテキストを残す
        return False, "paste_failed_text_in_clipboard"

    # 貼り付け後にクリップボードを復元
    time.sleep(restore_delay)
    if original_text is not None:
        set_clipboard(original_text)

    return True, "ok"
