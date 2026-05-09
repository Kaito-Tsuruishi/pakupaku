"""SLM フォールバック判定ロジック (15〜25% 発火率を目標)"""

from __future__ import annotations

from pakupaku.config import ROUTER_CONFIG
from pakupaku.parser import (
    ParsedSentence,
    count_root,
    find_marker_positions,
    has_parse_error,
    parse_complexity,
)
from pakupaku.repetition import (
    has_repeated_content_word,
    has_repetition_marker,
    load_repetition_markers,
    phrase_similarity_around,
)
from pakupaku.types import Sentence


def has_predicate_after_filtering(sentence: Sentence) -> bool:
    """フィラー・言い直しを除いた後に述語が残っているか"""
    visible = sentence.visible_tokens()
    return any(tok.pos in ("動詞", "形容詞", "助動詞") for tok in visible)


def needs_slm_fallback(
    sentence: Sentence, parsed: ParsedSentence
) -> tuple[bool, str | None]:
    """SLM フォールバックが必要か判定する

    Returns:
        (発火フラグ, 発火理由) のタプル。発火しない場合は (False, None)。
    """
    if not ROUTER_CONFIG.get("global_enable", True):
        return False, None

    # 1. マーカーありで類似度が低・境界
    if has_repetition_marker(sentence):
        markers = load_repetition_markers()
        for marker_idx in find_marker_positions(parsed, set(markers)):
            sim = phrase_similarity_around(parsed, marker_idx, n=5)
            if sim < ROUTER_CONFIG["similarity_threshold"]:
                return True, f"low_similarity_around_marker (sim={sim:.2f})"

    # 2. マーカーなしで同一内容語の繰り返し (B 型疑い)
    if has_repeated_content_word(sentence) and not has_repetition_marker(sentence):
        return True, "repeated_content_word_without_marker"

    # 3. 係り受け解析の破綻
    if has_parse_error(parsed):
        return True, "parse_error"
    if count_root(parsed) >= 2:
        return True, "multiple_roots"

    # 4. フィラー除去後に述語が消失
    if not has_predicate_after_filtering(sentence):
        return True, "predicate_lost_after_filtering"

    # 5. 極端に長い + 係り受けが複雑
    if (
        len(sentence.tokens) >= ROUTER_CONFIG["long_sentence_token_count"]
        and parse_complexity(parsed) > ROUTER_CONFIG["parse_complexity_threshold"]
    ):
        return True, "long_and_complex"

    return False, None
