"""句読点復元 (古典 NLP, 基本ルール)

文末助詞の後に「。」、接続助詞の後に「、」を入れる。
格助詞「が」(主語マーカー) は読点トリガーから除外。
読点の細かい配置・体言止め判定・列挙構造は SLM に任せる。
"""

from __future__ import annotations

from pakupaku.filler import collapse_consecutive_punctuation
from pakupaku.types import Sentence

# 文末となりやすい助動詞・助詞 (Sudachi 表層)
SENTENCE_END_AUX = frozenset(
    {
        "だ", "です", "ます", "でした", "ました",
        "ません", "ない", "ぬ", "た", "だった",
        "でしょう", "ましょう", "う", "よう",
    }
)

# 接続助詞のうち、読点を入れて自然なもの
# 注意: 古典 NLP では格助詞との区別が難しいので、強い接続助詞のみ採用
# - 格助詞「が」(主語) と紛らわしいため除外
# - 「から」「ので」も時間/起点の格助詞用法があるため除外
CONNECTIVE_PARTICLES_FOR_COMMA = frozenset(
    {"けど", "けれど", "けれども", "のに", "ても", "でも"}
)


def restore_punctuation(sentence: Sentence) -> str:
    """Sentence から整形済み文字列を生成 (句読点を補完)"""
    visible = sentence.visible_tokens()
    if not visible:
        return ""

    # 終助詞 (「ね」「よ」「な」等)、これらの前に読点を入れない
    _SENTENCE_FINAL_PARTICLES = {"ね", "よ", "な", "ぞ", "ぜ", "わ", "の", "さ", "か"}

    parts: list[str] = []
    for i, tok in enumerate(visible):
        parts.append(tok.surface)
        # 既に句読点があるなら何もしない
        if tok.surface in {"。", "、", "！", "？", "!", "?"}:
            continue
        # 接続助詞の後に読点 (品詞が助詞の場合のみ)
        if (
            tok.pos == "助詞"
            and tok.surface in CONNECTIVE_PARTICLES_FOR_COMMA
            and i + 1 < len(visible)
        ):
            next_tok = visible[i + 1]
            next_surface = next_tok.surface
            # 後ろが句読点なら不要
            if next_surface in {"。", "、", "！", "？"}:
                continue
            # 後ろが終助詞 (ね, よ 等) なら読点を入れない
            if next_tok.pos == "助詞" and next_surface in _SENTENCE_FINAL_PARTICLES:
                continue
            parts.append("、")

    text = "".join(parts)

    # 連続する句読点を 1 つに
    text = collapse_consecutive_punctuation(text)

    # 文末に句点を補う (体言止めも含めて、文として終わっていれば「。」を付ける)
    if text and text[-1] not in {"。", "、", "！", "？", "!", "?"}:
        text += "。"

    return text
