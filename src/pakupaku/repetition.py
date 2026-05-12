"""言い直し検出 (古典 NLP, A 型のみ)

A 型 = マーカー語 (「いや」「じゃなくて」等) の前後で類似フレーズがあるケース。
B〜F 型 (マーカーなし、部分置換、意味的言い直し等) は SLM に任せる。
"""

from __future__ import annotations

from functools import lru_cache

from pakupaku.config import REPETITION_MARKERS_PATH
from pakupaku.parser import (
    ParsedSentence,
    find_marker_positions,
    get_phrase_after,
    get_phrase_before,
)
from pakupaku.types import Sentence


@lru_cache(maxsize=1)
def load_repetition_markers() -> frozenset[str]:
    """言い直しマーカー辞書を読み込む"""
    markers: set[str] = set()
    if not REPETITION_MARKERS_PATH.exists():
        return frozenset()
    with open(REPETITION_MARKERS_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                markers.add(line)
    return frozenset(markers)


def _normalized_levenshtein(a: str, b: str) -> float:
    """正規化レーベンシュタイン類似度を 0.0〜1.0 で返す"""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    # 簡易 DP
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,
                dp[i][j - 1] + 1,
                dp[i - 1][j - 1] + cost,
            )
    distance = dp[m][n]
    return 1.0 - distance / max(m, n)


def phrase_similarity_around(parsed: ParsedSentence, marker_idx: int, n: int = 5) -> float:
    """マーカー前後の類似度を返す

    GiNZA が利用可能なら文節単位で比較 (精度高)。
    フォールバック時は前後 n トークンの単純な文字列比較。
    """
    from pakupaku.parser import get_bunsetu_after, get_bunsetu_before

    if marker_idx < 0 or marker_idx >= len(parsed.sentence.tokens):
        return 0.0
    marker_surface = parsed.sentence.tokens[marker_idx].surface

    # GiNZA 文節ベース (推奨)
    bunsetu_before = get_bunsetu_before(parsed, marker_surface)
    bunsetu_after = get_bunsetu_after(parsed, marker_surface)
    if bunsetu_before is not None and bunsetu_after is not None:
        # 文節末尾の助詞 (「、」「の」「を」など) を除いて比較
        b_before = _strip_trailing_particles(bunsetu_before)
        b_after = _strip_trailing_particles(bunsetu_after)
        return _normalized_levenshtein(b_before, b_after)

    # フォールバック: 前後 n トークンの文字列比較
    before = get_phrase_before(parsed, marker_idx, n=n)
    after = get_phrase_after(parsed, marker_idx, n=n)
    return _normalized_levenshtein(before, after)


def _strip_trailing_particles(text: str) -> str:
    """文節末尾の助詞・読点を取り除く

    「14時から」「14時から、」 → 「14時」
    「明日の」「明日の、」 → 「明日」
    """
    if not text:
        return text
    while text and text[-1] in {"、", "。", "の", "を", "に", "が", "は", "と", "で", "へ", "や", "か", "から"}:
        # 「から」のような複数文字は別処理
        if text.endswith("から"):
            text = text[:-2]
        else:
            text = text[:-1]
    return text


_AMBIGUOUS_SHORT_MARKERS = {"あ", "お"}


def has_repetition_marker(sentence: Sentence) -> bool:
    """文中にマーカー語が含まれるか

    位置の制約:
    - マーカー位置より前に名詞・動詞・形容詞 (内容語) が 1 つ以上ある (文頭フィラー除外)
    - 曖昧マーカー (「あ」「お」) は感動詞品詞のときのみ採用
    """
    markers = load_repetition_markers()
    seen_content = False
    for tok in sentence.tokens:
        if seen_content and tok.surface in markers:
            if tok.surface in _AMBIGUOUS_SHORT_MARKERS and tok.pos != "感動詞":
                pass
            else:
                return True
        if tok.pos in {"名詞", "動詞", "形容詞"}:
            seen_content = True
    return False


# 繰り返しチェックから除外する高頻度語 (汎用動詞・形式名詞)
_GENERIC_CONTENT_WORDS = frozenset(
    {
        # 汎用動詞 (「する」の活用、「ある」「いる」等)
        "し", "する", "さ", "せ", "あ", "あり", "ある", "い", "いる",
        "なっ", "なる", "なり", "なら", "やっ", "やる", "やり",
        "き", "く", "くる", "き", "こ",
        # 形式名詞・代名詞
        "こと", "もの", "の", "ところ", "とき", "ため",
        "それ", "これ", "あれ", "そう", "こう", "ああ",
        # 数値表現の単位
        "時", "分", "秒", "日", "月", "年", "回", "個", "本",
    }
)


def has_repeated_content_word(sentence: Sentence) -> bool:
    """同一の名詞・動詞の繰り返しがあるか (B 型疑い)

    汎用動詞 (する・ある等) と形式名詞 (こと・もの等) は除外する。
    """
    seen_content: dict[str, int] = {}
    for token in sentence.tokens:
        if token.is_filler or token.is_repetition:
            continue
        if token.pos not in ("名詞", "動詞"):
            continue
        if token.surface in _GENERIC_CONTENT_WORDS:
            continue
        # 1 文字の単独表記も繰り返し判定から除外 (「が」「て」等の助詞分割誤差対策)
        if len(token.surface) <= 1 and token.pos == "動詞":
            continue
        seen_content[token.surface] = seen_content.get(token.surface, 0) + 1
    return any(count >= 2 for count in seen_content.values())


def detect_repetition_simple(sentence: Sentence, parsed: ParsedSentence) -> Sentence:
    """A 型言い直しを検出してマークする

    方針: マーカー語が文中 (内容語の後) に現れたら言い直しと判断し、
    マーカー直前の 1 文節を repetition マークする。

    類似度判定はしない (「リリース」と「デプロイ」のように意味的には言い直しでも
    表層が完全に違うケースを取り逃すため)。

    マーカーは辞書に厳選した語のみ (「いや」「じゃなくて」「あ」「お」等)。
    フィラー「あ」を文中言い直しと誤判定しないために、find_marker_positions 側で
    「文頭以外」「内容語の後」という制約を入れている。
    """
    markers = load_repetition_markers()
    marker_positions = find_marker_positions(parsed, set(markers))

    for marker_idx in marker_positions:
        _mark_before_marker_as_repetition(sentence, parsed, marker_idx)

    return sentence


def _mark_before_marker_as_repetition(
    sentence: Sentence, parsed: ParsedSentence, marker_idx: int
) -> None:
    """マーカー位置より前の n 文節を言い直しとしてマーク

    n はマーカー後の文節数を上限に決定する (前後対称の言い直し範囲を狙う)。
    例: 「Redisのコネクション、あ、PostgreSQLのコネクションが切れてました」
        → マーカー後は 3 文節 (「PostgreSQLのコネクションが」「切れて」「ました」)
        → 前は最大 2 文節相当 (「Redisのコネクション、」) を言い直しと判定

    GiNZA 不在時は前 5 トークンをマーク (フォールバック)。
    """
    if marker_idx <= 0 or marker_idx >= len(sentence.tokens):
        return
    target = sentence.tokens[marker_idx]

    from pakupaku.parser import (
        count_bunsetu_after_marker,
        get_bunsetu_before,
    )

    # マーカー後の文節数 (上限 2 で前を取る、長すぎる削除を避ける)
    after_count = count_bunsetu_after_marker(parsed, target.surface)
    n_bunsetu = min(2, max(1, after_count))

    bunsetu_text = get_bunsetu_before(parsed, target.surface, n_bunsetu=n_bunsetu)

    if bunsetu_text:
        _mark_tokens_matching_text(sentence, marker_idx, bunsetu_text)
    else:
        count = 0
        for j in range(marker_idx - 1, -1, -1):
            if sentence.tokens[j].is_filler:
                continue
            if count >= 5:
                break
            sentence.tokens[j].is_repetition = True
            count += 1

    target.is_repetition = True


def _mark_tokens_matching_text(
    sentence: Sentence, marker_idx: int, text: str
) -> None:
    """マーカー直前のトークン列のうち、`text` の表層を構成する範囲を repetition マーク

    GiNZA の文節と Sudachi の形態素境界は通常一致するが、軽い差異 (Sudachi の補助記号扱い等)
    があるため、表層文字列の suffix 一致で判定する。

    対称差分による絞り込み: マーカー後にも同じ文字列がある場合は repetition マークしない。
    例: before='Node.jsは18、', after='20を入れれば' のとき
        before の 'Node.jsは' は after にないので、これは「js は 18 までが言い直し対象」
        ではなく、「Node.js は」までは新表現にも引き継がれるべき修飾要素と判定する。
        単純な実装としてここでは「マーカー直前から、最後の名詞・数値の固まりまで」を対象に。
    """
    if not text:
        return

    # 候補: marker_idx より前のトークンを末尾から逆順に集めて、結合長が text 長以上になるまで取る
    candidate_indices: list[int] = []
    accumulated = ""
    for j in range(marker_idx - 1, -1, -1):
        candidate_indices.append(j)
        accumulated = sentence.tokens[j].surface + accumulated
        if len(accumulated) >= len(text):
            break

    # 末尾が text と一致するか
    if accumulated.endswith(text) or text in accumulated:
        # 一致する範囲を仮マーク
        # ただし、マーカー後の文節と共通する prefix があれば、それは「修飾要素」として残す
        # 例: before='14時から、'、after='15時から' → 「時から」が共通 → 「14」だけ言い直し
        marked_indices = list(candidate_indices)
        common_prefix_len = _find_common_modifier_prefix(sentence, marker_idx, candidate_indices)
        if common_prefix_len > 0:
            # 末尾 common_prefix_len トークン分は repetition マークしない
            marked_indices = candidate_indices[common_prefix_len:]
        for j in marked_indices:
            if not sentence.tokens[j].is_filler:
                sentence.tokens[j].is_repetition = True
    else:
        # 一致しなければ最低限「マーカー直前の連続非フィラー」をマーク
        count = 0
        for j in range(marker_idx - 1, -1, -1):
            if sentence.tokens[j].is_filler:
                continue
            tok = sentence.tokens[j]
            tok.is_repetition = True
            count += 1
            # 文末助詞 / 句読点 が来たら止まる
            if count >= 1 and (
                tok.surface in {"。", "、", "！", "？"}
                or (tok.pos == "助詞" and j > 0 and sentence.tokens[j - 1].pos == "名詞")
            ):
                break
            if count >= 8:
                break


def _find_common_modifier_prefix(
    sentence: Sentence, marker_idx: int, candidate_indices: list[int]
) -> int:
    """マーカー前後の共通修飾要素 (語尾の同じ語) のトークン数を返す

    candidate_indices はマーカーから逆順 (新しい順) に並んでいる。
    マーカー後のトークン列の prefix と、candidate (マーカー前の suffix 順) を逆向きに比較し、
    両方で一致する語があれば、その数を返す。

    例:
      before tokens: [14, 時, から, 、]  (candidate_indices は逆順 [、, から, 時, 14])
      after tokens:  [15, 時, から, 会議, です]
      → 「時」「から」が共通 → 戻り値は 2 (これらは repetition マークしない)
    """
    # マーカー後のトークン列を取得 (フィラーを除く)
    after_surfaces: list[str] = []
    for j in range(marker_idx + 1, len(sentence.tokens)):
        tok = sentence.tokens[j]
        if tok.is_filler or tok.is_repetition:
            continue
        if tok.surface in {"、", "。", "!", "?", "！", "？"}:
            continue
        after_surfaces.append(tok.surface)

    if not after_surfaces or not candidate_indices:
        return 0

    # candidate_indices は逆順 (末尾→先頭)。
    # マーカー前の末尾 (=最も新しい/マーカーに近い) から順に、after_surfaces の先頭と比較する
    # ただし読点・補助記号はスキップ
    common = 0
    after_pos = 0
    # マーカー前末尾から順番に
    for ci in candidate_indices:
        tok = sentence.tokens[ci]
        if tok.surface in {"、", "。", "!", "?"}:
            common += 1  # 読点はカウントするが比較しない
            continue
        if after_pos >= len(after_surfaces):
            break
        if tok.surface == after_surfaces[after_pos]:
            common += 1
            after_pos += 1
        else:
            break

    return common
