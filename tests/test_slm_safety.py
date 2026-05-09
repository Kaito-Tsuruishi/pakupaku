"""SLM 出力の安全装置 (_verify_safe_output) のテスト

実 SLM を呼ばずに、検証ロジック単体をテストする。
"""

import pytest

from pakupaku.slm import SLMUnsafeOutput, _extract_alnum_tokens, _verify_safe_output


def test_safe_output_passes():
    """通常のフィラー除去はパスする"""
    _verify_safe_output(
        "えーと、明日の会議に参加します",
        "明日の会議に参加します。",
    )


def test_empty_output_rejected():
    with pytest.raises(SLMUnsafeOutput, match="empty"):
        _verify_safe_output("明日の会議", "")


def test_too_short_rejected():
    """40% 未満は要約しすぎ判定"""
    with pytest.raises(SLMUnsafeOutput, match="too short"):
        _verify_safe_output(
            "明日の会議では新機能のリリース計画を議論します",
            "会議",
        )


def test_too_long_rejected():
    """150% 超は補完判定"""
    with pytest.raises(SLMUnsafeOutput, match="too long"):
        _verify_safe_output(
            "了解です",
            "了解しました。明日までに対応いたします。よろしくお願いいたします。承知しました。",
        )


def test_number_loss_rejected():
    """原文の数値が出力で消えたら不正"""
    with pytest.raises(SLMUnsafeOutput, match="missing"):
        _verify_safe_output(
            "14時から会議です",
            "会議です。",
        )


def test_english_token_loss_rejected():
    """原文の英字 (固有名詞) が出力で消えたら不正"""
    with pytest.raises(SLMUnsafeOutput, match="missing"):
        _verify_safe_output(
            "GitHubに上げました",
            "上げました。",
        )


def test_extract_alnum_basic():
    assert _extract_alnum_tokens("14時から") == {"14"}
    assert _extract_alnum_tokens("APIエンドポイント") == {"API"}
    assert _extract_alnum_tokens("Pull Request 番号 123") == {"Pull", "Request", "123"}
    assert _extract_alnum_tokens("日本語のみ") == set()


def test_safe_output_keeps_numbers():
    """原文の数値が出力に残っていれば OK"""
    _verify_safe_output(
        "えーと、14時から会議です",
        "14時から会議です。",
    )


def test_baseline_overrides_strict_check():
    """baseline (古典結果) を渡せば、古典が消した語は SLM が消しても OK"""
    # 古典が「Node.jsの話を、いや」を削除済みなら、SLM 出力に Node, js が無くてもセーフ
    _verify_safe_output(
        input_text="Node.jsの話を、いやPostgreSQLの話をします",
        output_text="PostgreSQLの話をします。",
        baseline="PostgreSQLの話をします",  # 古典が言い直しを消した結果
    )


def test_baseline_still_catches_extra_loss():
    """baseline と比べて SLM が新たに英数字を消した場合は検知"""
    # 古典結果には API が残っているのに SLM が消したら不正
    with pytest.raises(SLMUnsafeOutput, match="missing"):
        _verify_safe_output(
            input_text="えっと、APIサーバーで500、いや503エラーが出てます",
            output_text="APIサーバーでエラーが出てます。",  # 500/503 が両方消えた
            baseline="APIサーバーで503エラーが出てます",
        )
