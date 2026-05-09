"""ルーター発火条件のテスト

GiNZA に依存する条件は実機でしか動かないため、has_repeated_content_word /
has_predicate_after_filtering 等の Sentence のみで判定可能なものをテストする。
"""

from pakupaku.router import has_predicate_after_filtering
from pakupaku.types import Sentence, Token


def test_predicate_present():
    tokens = [
        Token(surface="行き", pos="動詞"),
        Token(surface="ます", pos="助動詞"),
    ]
    s = Sentence(tokens=tokens, original_text="行きます")
    assert has_predicate_after_filtering(s) is True


def test_predicate_lost_when_all_filler():
    tokens = [
        Token(surface="えーと", pos="感動詞", is_filler=True),
        Token(surface="まぁ", pos="感動詞", is_filler=True),
        Token(surface="あの", pos="感動詞", is_filler=True),
    ]
    s = Sentence(tokens=tokens, original_text="えーと、まぁ、あの")
    assert has_predicate_after_filtering(s) is False


def test_predicate_with_only_nouns():
    tokens = [
        Token(surface="明日", pos="名詞"),
        Token(surface="の", pos="助詞"),
        Token(surface="会議", pos="名詞"),
    ]
    s = Sentence(tokens=tokens, original_text="明日の会議")
    # 体言止め: 動詞・形容詞・助動詞なし → False
    assert has_predicate_after_filtering(s) is False
