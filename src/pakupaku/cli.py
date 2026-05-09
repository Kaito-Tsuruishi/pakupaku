"""pakupaku CLI エントリポイント

日常運用は Hammerspoon のホットキー (Ctrl+Shift+Space) で行うため、
CLI コマンドはセットアップ・保守・トラブル時にのみ使う。

サブコマンド:
- start / stop / restart / status: launchd 経由の daemon 制御
- slm-off / slm-on: SLM の有効/無効切り替え (plist を書き換えて再起動)
- text: テキスト整形のみ (デバッグ用)
- daemon: 常駐デーモン本体 (launchd plist から呼ばれる、help から隠す)
"""

from __future__ import annotations

import argparse
import json
import plistlib
import shutil
import socket
import subprocess
import sys
from pathlib import Path

from pakupaku.config import SOCKET_PATH

PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / "com.pakupaku.daemon.plist"
PLIST_BACKUP_PATH = PLIST_PATH.with_suffix(PLIST_PATH.suffix + ".bak")
LAUNCHD_LABEL = "com.pakupaku.daemon"
NO_SLM_FLAG = "--no-slm"


# ===== daemon (内部用、help から隠す) =====


def cmd_daemon(args: argparse.Namespace) -> int:
    from pakupaku.daemon import main as daemon_main

    daemon_main(no_slm=getattr(args, "no_slm", False))
    return 0


# ===== launchd 制御 =====


def _launchctl_load() -> tuple[bool, str]:
    if not PLIST_PATH.exists():
        return False, f"plist が見つかりません: {PLIST_PATH} (setup.sh を実行してください)"
    try:
        subprocess.run(
            ["launchctl", "load", "-w", str(PLIST_PATH)],
            check=True,
            capture_output=True,
            text=True,
        )
        return True, "loaded"
    except subprocess.CalledProcessError as e:
        return False, e.stderr.strip() or str(e)


def _launchctl_unload() -> tuple[bool, str]:
    if not PLIST_PATH.exists():
        return False, f"plist が見つかりません: {PLIST_PATH}"
    try:
        subprocess.run(
            ["launchctl", "unload", str(PLIST_PATH)],
            check=True,
            capture_output=True,
            text=True,
        )
        return True, "unloaded"
    except subprocess.CalledProcessError as e:
        return False, e.stderr.strip() or str(e)


def _daemon_pid() -> int | None:
    """launchctl list から daemon の PID を取得 (動いていなければ None)"""
    try:
        result = subprocess.run(
            ["launchctl", "list"], capture_output=True, text=True, check=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[2] == LAUNCHD_LABEL:
            try:
                pid = int(parts[0])
                return pid if pid > 0 else None
            except ValueError:
                return None
    return None


def cmd_start(args: argparse.Namespace) -> int:
    if _daemon_pid() is not None:
        print("pakupaku daemon は既に起動しています")
        return 0
    ok, msg = _launchctl_load()
    if ok:
        print("✓ pakupaku daemon を起動しました")
        return 0
    print(f"✗ 起動に失敗しました: {msg}", file=sys.stderr)
    return 1


def cmd_stop(args: argparse.Namespace) -> int:
    if _daemon_pid() is None and not PLIST_PATH.exists():
        print("pakupaku daemon は登録されていません")
        return 0
    ok, msg = _launchctl_unload()
    if ok:
        print("✓ pakupaku daemon を停止しました")
        return 0
    print(f"✗ 停止に失敗しました: {msg}", file=sys.stderr)
    return 1


def cmd_restart(args: argparse.Namespace) -> int:
    _launchctl_unload()  # 既に止まっていてもエラー無視
    ok, msg = _launchctl_load()
    if ok:
        print("✓ pakupaku daemon を再起動しました")
        return 0
    print(f"✗ 再起動に失敗しました: {msg}", file=sys.stderr)
    return 1


# ===== SLM の有効/無効切り替え =====


def add_no_slm_flag(plist_data: dict) -> tuple[dict, bool]:
    """plist の ProgramArguments に --no-slm を追加した dict を返す

    Returns:
        (新しい dict, 変更があったか)
    """
    args = list(plist_data.get("ProgramArguments", []))
    if NO_SLM_FLAG in args:
        return plist_data, False
    args.append(NO_SLM_FLAG)
    new_data = dict(plist_data)
    new_data["ProgramArguments"] = args
    return new_data, True


def remove_no_slm_flag(plist_data: dict) -> tuple[dict, bool]:
    """plist の ProgramArguments から --no-slm を削除した dict を返す

    Returns:
        (新しい dict, 変更があったか)
    """
    args = list(plist_data.get("ProgramArguments", []))
    if NO_SLM_FLAG not in args:
        return plist_data, False
    args = [a for a in args if a != NO_SLM_FLAG]
    new_data = dict(plist_data)
    new_data["ProgramArguments"] = args
    return new_data, True


def is_no_slm_enabled(plist_data: dict) -> bool:
    """plist が SLM 無効モードかどうか"""
    return NO_SLM_FLAG in plist_data.get("ProgramArguments", [])


def _read_plist() -> dict | None:
    if not PLIST_PATH.exists():
        return None
    with open(PLIST_PATH, "rb") as f:
        return plistlib.load(f)


def _write_plist(data: dict) -> None:
    """plist を書き出す (バックアップを作成してから書き換え)"""
    if PLIST_PATH.exists():
        shutil.copy2(PLIST_PATH, PLIST_BACKUP_PATH)
    with open(PLIST_PATH, "wb") as f:
        plistlib.dump(data, f)


def _toggle_slm(disable: bool) -> int:
    """SLM の有効/無効を切り替える共通処理"""
    plist_data = _read_plist()
    if plist_data is None:
        print(f"✗ plist が見つかりません: {PLIST_PATH}", file=sys.stderr)
        print("  setup.sh を実行してから再度試してください", file=sys.stderr)
        return 1

    if disable:
        new_data, changed = add_no_slm_flag(plist_data)
        already_msg = "すでに SLM 無効モードです (--no-slm が設定済み)"
        success_msg = "✓ SLM を無効化しました"
        info_msg = "  メモリ約 3.4GB が解放されます。再起動完了まで 30 秒程度かかります"
    else:
        new_data, changed = remove_no_slm_flag(plist_data)
        already_msg = "すでに SLM 有効モードです"
        success_msg = "✓ SLM を有効化しました"
        info_msg = "  SLM のロード中です。完了まで 1 分程度かかります"

    if not changed:
        print(already_msg)
        return 0

    try:
        _write_plist(new_data)
    except Exception as e:
        print(f"✗ plist の書き換えに失敗しました: {e}", file=sys.stderr)
        return 1

    _launchctl_unload()
    ok, msg = _launchctl_load()
    if not ok:
        print(f"✗ daemon の再起動に失敗しました: {msg}", file=sys.stderr)
        print(f"  plist のバックアップ: {PLIST_BACKUP_PATH}", file=sys.stderr)
        return 1

    print(success_msg)
    print(info_msg)
    return 0


def cmd_slm_off(args: argparse.Namespace) -> int:
    return _toggle_slm(disable=True)


def cmd_slm_on(args: argparse.Namespace) -> int:
    return _toggle_slm(disable=False)


# ===== status =====


def _hammerspoon_running() -> bool:
    try:
        result = subprocess.run(
            ["pgrep", "-x", "Hammerspoon"], capture_output=True, text=True
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def _process_rss_mb(pid: int) -> float | None:
    try:
        result = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(pid)],
            capture_output=True,
            text=True,
            check=True,
        )
        kb = int(result.stdout.strip())
        return kb / 1024.0
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
        return None


def _query_daemon_status() -> dict | None:
    """daemon にIPCでstatusを問い合わせる"""
    if not SOCKET_PATH.exists():
        return None
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect(str(SOCKET_PATH))
        s.sendall(b"status\n")
        chunks = []
        while True:
            data = s.recv(4096)
            if not data:
                break
            chunks.append(data)
        s.close()
        raw = b"".join(chunks).decode("utf-8", errors="replace").strip()
        if not raw:
            return None
        return json.loads(raw)
    except Exception:
        return None


def cmd_status(args: argparse.Namespace) -> int:
    pid = _daemon_pid()
    daemon_info = _query_daemon_status() if pid is not None else None

    print("pakupaku status")
    print("─────────────────")

    if pid is not None:
        print(f"daemon:      ● running (pid {pid})")
    else:
        print("daemon:      ○ not running")

    if SOCKET_PATH.exists():
        print(f"socket:      ✓ {SOCKET_PATH}")
    else:
        print(f"socket:      ✗ {SOCKET_PATH} (not found)")

    if _hammerspoon_running():
        print("hammerspoon: ● running")
    else:
        print("hammerspoon: ○ not running")

    plist_data = _read_plist()
    plist_no_slm = is_no_slm_enabled(plist_data) if plist_data is not None else False

    if daemon_info is not None:
        if daemon_info.get("slm_loaded"):
            print(f"SLM:         ✓ loaded ({daemon_info.get('slm_model')})")
        elif plist_no_slm:
            print("SLM:         ○ disabled (--no-slm mode)")
        else:
            print("SLM:         ○ not loaded")
        print(f"STT:         ✓ {daemon_info.get('stt_model')}")
        if daemon_info.get("recording"):
            print("recording:   ● in progress")
    else:
        if plist_no_slm:
            print("SLM:         ○ disabled (--no-slm mode)")
        else:
            print("SLM:         ? (daemon に問い合わせ不可)")
        print("STT:         ? (daemon に問い合わせ不可)")

    if pid is not None:
        rss = _process_rss_mb(pid)
        if rss is not None:
            print(f"memory:      ~{rss / 1024:.1f} GB")

    return 0


# ===== text 整形 =====


def cmd_text(args: argparse.Namespace) -> int:
    """テキストを整形して標準出力する"""
    from pakupaku.pipeline import process

    if args.input:
        text = args.input
    elif args.file:
        with open(args.file, encoding="utf-8") as f:
            text = f.read().strip()
    else:
        text = sys.stdin.read().strip()

    if not text:
        return 0

    slm_model = None
    if not args.no_slm:
        try:
            from pakupaku.model_loader import get_slm

            slm_model = get_slm()
        except Exception as e:
            print(f"[pakupaku] SLM load failed: {e}, continuing without SLM", file=sys.stderr)

    force_slm = args.always_slm and slm_model is not None
    result = process(text, slm_model=slm_model, force_slm=force_slm)

    if args.verbose:
        print(f"[input] {result.input_text}", file=sys.stderr)
        print(
            f"[meta] used_slm={result.used_slm}, reason={result.trigger_reason}, "
            f"latency={result.latency_ms:.1f}ms",
            file=sys.stderr,
        )
    print(result.output_text)
    return 0


# ===== parser =====


class _HideDaemonFormatter(argparse.HelpFormatter):
    """`paku --help` の subcommand 一覧から `daemon` を隠すための formatter"""

    def _format_action(self, action):
        if isinstance(action, argparse._SubParsersAction):
            action._choices_actions = [
                a for a in action._choices_actions if a.dest != "daemon"
            ]
            if "daemon" in action.choices:
                action.choices = {k: v for k, v in action.choices.items() if k != "daemon"}
        return super()._format_action(action)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paku",
        description="ローカル音声入力後処理ツール (日常運用は Ctrl+Shift+Space で実行)",
        formatter_class=_HideDaemonFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_start = sub.add_parser("start", help="daemon を起動")
    p_start.set_defaults(func=cmd_start)

    p_stop = sub.add_parser("stop", help="daemon を停止")
    p_stop.set_defaults(func=cmd_stop)

    p_restart = sub.add_parser("restart", help="daemon を再起動")
    p_restart.set_defaults(func=cmd_restart)

    p_status = sub.add_parser("status", help="動作状態を表示")
    p_status.set_defaults(func=cmd_status)

    p_slm_off = sub.add_parser("slm-off", help="SLM を無効化してメモリを節約")
    p_slm_off.set_defaults(func=cmd_slm_off)

    p_slm_on = sub.add_parser("slm-on", help="SLM を有効化 (通常モードに戻す)")
    p_slm_on.set_defaults(func=cmd_slm_on)

    p_text = sub.add_parser("text", help="テキスト整形のみ実行 (デバッグ用)")
    p_text.add_argument("--input", "-i", help="整形対象テキスト")
    p_text.add_argument("--file", "-f", help="入力ファイル")
    p_text.add_argument("--no-slm", action="store_true", help="SLM 無効化")
    p_text.add_argument(
        "--always-slm", action="store_true", help="常に SLM 発火 (router 無視)"
    )
    p_text.add_argument("--verbose", "-v", action="store_true", help="メタ情報を表示")
    p_text.set_defaults(func=cmd_text)

    # daemon: launchd plist から呼ばれる内部コマンド (HelpFormatter で help から除外)
    p_daemon = sub.add_parser("daemon")
    p_daemon.add_argument(
        "--no-slm", action="store_true", help="SLM をロードせずに起動 (メモリ節約モード)"
    )
    p_daemon.set_defaults(func=cmd_daemon)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
