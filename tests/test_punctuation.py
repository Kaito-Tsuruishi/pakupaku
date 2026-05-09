"""句読点復元のテスト"""

from pakupaku.punctuation import restore_punctuation
from pakupaku.types import Sentence, Token


def test_appends_period_after_masu():
    tokens = [
        Token(surface="参加", pos="名詞"),
        Token(surface="し", pos="動詞"),
        Token(surface="ます", pos="助動詞"),
    ]
    s = Sentence(tokens=tokens, original_text="参加します")
    assert restore_punctuation(s) == "参加します。"


def test_no_double_period():
    tokens = [
        Token(surface="参加", pos="名詞"),
        Token(surface="し", pos="動詞"),
        Token(surface="ます", pos="助動詞"),
        Token(surface="。", pos="補助記号"),
    ]
    s = Sentence(tokens=tokens, original_text="参加します。")
    out = restore_punctuation(s)
    assert out.count("。") == 1


def test_inserts_comma_after_connective():
    tokens = [
        Token(surface="行く", pos="動詞"),
        Token(surface="けど", pos="助詞"),
        Token(surface="遅れる", pos="動詞"),
    ]
    s = Sentence(tokens=tokens, original_text="行くけど遅れる")
    out = restore_punctuation(s)
    assert "けど、" in out


def test_skips_filler_in_output():
    tokens = [
        Token(surface="えーと", pos="感動詞", is_filler=True),
        Token(surface="行き", pos="動詞"),
        Token(surface="ます", pos="助動詞"),
    ]
    s = Sentence(tokens=tokens, original_text="えーと、行きます")
    out = restore_punctuation(s)
    assert "えーと" not in out
    assert "行きます" in out


def test_empty_returns_empty():
    s = Sentence(tokens=[], original_text="")
    assert restore_punctuation(s) == ""
