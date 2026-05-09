"""フィラー除去のテスト

Note: load_filler_dict() の遅延ロードを利用するため、Sudachi 依存テストは除外。
辞書のロードと判定ロジックだけ確認する。
"""

from pakupaku.filler import _is_filler_token, load_filler_dict
from pakupaku.types import Sentence, Token


def test_load_filler_dict_returns_set():
    fillers = load_filler_dict()
    assert isinstance(fillers, frozenset)
    assert "えーと" in fillers
    assert "まぁ" in fillers
    assert "うーん" in fillers


def test_load_filler_dict_excludes_meaningful_words():
    """意味のある語 (副詞・接続詞・呼びかけ) は辞書に含めない方針"""
    fillers = load_filler_dict()
    # 副詞として意味あり
    assert "ちょっと" not in fillers
    # 接続詞として意味あり
    assert "それで" not in fillers
    assert "だから" not in fillers
    # 呼びかけ・謝罪として意味あり
    assert "すみません" not in fillers
    # 連体詞として意味あり (「あの本」等)
    assert "あの" not in fillers
    assert "その" not in fillers
    assert "この" not in fillers


def test_is_filler_token_dictionary_match():
    fillers = load_filler_dict()
    assert _is_filler_token("えーと", "名詞", fillers)
    assert _is_filler_token("まぁ", "感動詞", fillers)


def test_is_filler_token_pos_match():
    """辞書になくても感動詞ならフィラー"""
    fillers = frozenset()
    assert _is_filler_token("おっと", "感動詞", fillers)


def test_is_filler_token_negative():
    fillers = load_filler_dict()
    assert not _is_filler_token("会議", "名詞", fillers)
    assert not _is_filler_token("参加", "動詞", fillers)


def test_remove_fillers_marks_tokens():
    """直接 Token 列を渡してマーク処理だけ確認 (Sudachi なしでテスト)"""
    from pakupaku.filler import remove_fillers

    tokens = [
        Token(surface="えーと", pos="感動詞"),
        Token(surface="明日", pos="名詞"),
        Token(surface="の", pos="助詞"),
        Token(surface="会議", pos="名詞"),
    ]
    s = Sentence(tokens=tokens, original_text="えーと、明日の会議")
    result = remove_fillers(s)
    assert result.tokens[0].is_filler is True
    assert result.tokens[1].is_filler is False
    assert result.tokens[2].is_filler is False
    assert result.tokens[3].is_filler is False
