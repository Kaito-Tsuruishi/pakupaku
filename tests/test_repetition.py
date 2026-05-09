"""言い直し検出 / 編集距離のテスト"""

from pakupaku.repetition import (
    _normalized_levenshtein,
    has_repeated_content_word,
    load_repetition_markers,
)
from pakupaku.types import Sentence, Token


def test_load_repetition_markers():
    markers = load_repetition_markers()
    assert "いや" in markers
    assert "じゃなくて" in markers


def test_normalized_levenshtein_identical():
    assert _normalized_levenshtein("abc", "abc") == 1.0


def test_normalized_levenshtein_completely_different():
    sim = _normalized_levenshtein("abc", "xyz")
    assert 0.0 <= sim <= 0.5


def test_normalized_levenshtein_empty():
    assert _normalized_levenshtein("", "") == 1.0
    assert _normalized_levenshtein("", "x") == 0.0


def test_normalized_levenshtein_partial_match():
    """「明日の会議」と「明後日の会議」は類似度 0.6 以上のはず"""
    sim = _normalized_levenshtein("明日の会議", "明後日の会議")
    assert sim > 0.6


def test_has_repeated_content_word():
    tokens = [
        Token(surface="明日", pos="名詞"),
        Token(surface="の", pos="助詞"),
        Token(surface="会議", pos="名詞"),
        Token(surface="、", pos="補助記号"),
        Token(surface="明日", pos="名詞"),  # 重複
        Token(surface="の", pos="助詞"),
        Token(surface="予定", pos="名詞"),
    ]
    s = Sentence(tokens=tokens, original_text="")
    assert has_repeated_content_word(s) is True


def test_has_no_repeated_content_word():
    tokens = [
        Token(surface="明日", pos="名詞"),
        Token(surface="の", pos="助詞"),
        Token(surface="会議", pos="名詞"),
    ]
    s = Sentence(tokens=tokens, original_text="")
    assert has_repeated_content_word(s) is False
