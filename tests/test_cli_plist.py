"""CLI の plist 編集ロジックのテスト

実際の plist ファイルや launchctl は触らず、純粋関数だけをテストする。
"""

from __future__ import annotations

from pakupaku.cli import (
    NO_SLM_FLAG,
    add_no_slm_flag,
    is_no_slm_enabled,
    remove_no_slm_flag,
)


def _base_plist() -> dict:
    """setup.sh が install_launchd.sh 経由で生成する plist の構造を模した dict"""
    return {
        "Label": "com.pakupaku.daemon",
        "ProgramArguments": [
            "/Users/test/.venv/bin/python",
            "-m",
            "pakupaku.cli",
            "daemon",
        ],
        "WorkingDirectory": "/Users/test/pakupaku",
        "RunAtLoad": True,
    }


def test_add_no_slm_flag_appends():
    plist = _base_plist()
    new, changed = add_no_slm_flag(plist)
    assert changed is True
    assert new["ProgramArguments"][-1] == NO_SLM_FLAG
    assert new["ProgramArguments"][:-1] == plist["ProgramArguments"]


def test_add_no_slm_flag_idempotent():
    plist = _base_plist()
    plist["ProgramArguments"].append(NO_SLM_FLAG)
    new, changed = add_no_slm_flag(plist)
    assert changed is False
    # 重複しない
    assert new["ProgramArguments"].count(NO_SLM_FLAG) == 1


def test_remove_no_slm_flag_removes():
    plist = _base_plist()
    plist["ProgramArguments"].append(NO_SLM_FLAG)
    new, changed = remove_no_slm_flag(plist)
    assert changed is True
    assert NO_SLM_FLAG not in new["ProgramArguments"]


def test_remove_no_slm_flag_idempotent():
    plist = _base_plist()
    new, changed = remove_no_slm_flag(plist)
    assert changed is False
    assert new["ProgramArguments"] == plist["ProgramArguments"]


def test_other_keys_preserved_on_add():
    plist = _base_plist()
    new, _ = add_no_slm_flag(plist)
    for key in ("Label", "WorkingDirectory", "RunAtLoad"):
        assert new[key] == plist[key]


def test_other_keys_preserved_on_remove():
    plist = _base_plist()
    plist["ProgramArguments"].append(NO_SLM_FLAG)
    new, _ = remove_no_slm_flag(plist)
    for key in ("Label", "WorkingDirectory", "RunAtLoad"):
        assert new[key] == plist[key]


def test_is_no_slm_enabled_true():
    plist = _base_plist()
    plist["ProgramArguments"].append(NO_SLM_FLAG)
    assert is_no_slm_enabled(plist) is True


def test_is_no_slm_enabled_false():
    plist = _base_plist()
    assert is_no_slm_enabled(plist) is False


def test_is_no_slm_enabled_empty_args():
    assert is_no_slm_enabled({"ProgramArguments": []}) is False
    assert is_no_slm_enabled({}) is False


def test_add_does_not_mutate_input():
    """元の dict を破壊しない (副作用なし)"""
    plist = _base_plist()
    original_args = list(plist["ProgramArguments"])
    add_no_slm_flag(plist)
    assert plist["ProgramArguments"] == original_args


def test_remove_does_not_mutate_input():
    plist = _base_plist()
    plist["ProgramArguments"].append(NO_SLM_FLAG)
    original_args = list(plist["ProgramArguments"])
    remove_no_slm_flag(plist)
    assert plist["ProgramArguments"] == original_args
