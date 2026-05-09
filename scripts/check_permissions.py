"""pakupaku に必要な macOS 権限がすべて付いているか確認するスクリプト

実行: uv run python scripts/check_permissions.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def check_microphone() -> bool:
    """マイク権限の確認 (短い録音を試みる)"""
    print("[1/3] マイク権限を確認中...")
    try:
        import sounddevice as sd
        import numpy as np

        # 0.1 秒だけ録音してみる
        sd.rec(int(0.1 * 16000), samplerate=16000, channels=1, dtype="float32", blocking=True)
        print("  ✓ マイク権限あり (録音テスト成功)")
        return True
    except Exception as e:
        print(f"  ✗ マイク権限エラー: {e}")
        return False


def check_clipboard() -> bool:
    """クリップボード書き込みの確認"""
    print("[2/3] クリップボード操作を確認中...")
    try:
        from pakupaku.clipboard import get_clipboard, set_clipboard

        original, _ = get_clipboard()
        test_text = "pakupaku permission test 12345"
        set_clipboard(test_text)
        check, _ = get_clipboard()
        # 元に戻す
        if original is not None:
            set_clipboard(original)
        if check == test_text:
            print("  ✓ クリップボード操作 OK")
            return True
        else:
            print(f"  ✗ クリップボードへの書き込みが反映されない: got={check!r}")
            return False
    except Exception as e:
        print(f"  ✗ クリップボードエラー: {e}")
        return False


def check_accessibility_paste() -> bool:
    """アクセシビリティ権限の確認 (osascript で keystroke が通るか)

    注: 実際に ⌘V を発火するわけではなく、System Events に問い合わせるだけ
    """
    print("[3/3] アクセシビリティ権限を確認中...")
    try:
        result = subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to get name of first process whose frontmost is true',
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0:
            print(f"  ✓ アクセシビリティ権限あり (フロントアプリ: {result.stdout.strip()})")
            return True
        else:
            print(f"  ✗ アクセシビリティ権限エラー: {result.stderr.strip()}")
            return False
    except Exception as e:
        print(f"  ✗ osascript 実行失敗: {e}")
        return False


def main() -> int:
    print("===================")
    print("pakupaku 権限チェック")
    print("===================")
    print()

    results = [
        check_microphone(),
        check_clipboard(),
        check_accessibility_paste(),
    ]

    print()
    print("===================")
    if all(results):
        print("✓ すべての権限が付与されています")
        print("  次のステップ:")
        print("    1. paku status                # daemon が起動しているか確認")
        print("    2. Hammerspoon Reload Config  # メニューバーアイコンから")
        print("    3. Ctrl+Shift+Space           # 任意のエディタで動作テスト")
        return 0
    else:
        print("✗ 不足している権限があります")
        print("  bash scripts/open_permissions.sh で設定画面を開きます")
        return 1


if __name__ == "__main__":
    sys.exit(main())
