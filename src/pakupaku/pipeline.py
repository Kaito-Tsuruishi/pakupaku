"""整形パイプラインのオーケストレーション"""

from __future__ import annotations

import time
from typing import Any

from pakupaku.filler import remove_fillers
from pakupaku.parser import parse_dependency
from pakupaku.punctuation import restore_punctuation
from pakupaku.repetition import detect_repetition_simple
from pakupaku.router import needs_slm_fallback
from pakupaku.tokenizer import tokenize
from pakupaku.types import ProcessingResult


def process(text: str, slm_model: Any | None = None, force_slm: bool = False) -> ProcessingResult:
    """テキストを整形パイプラインに通す

    Args:
        text: 整形対象のテキスト (Whisper 出力想定)
        slm_model: SLM の (model, tokenizer) ペア。None なら SLM フォールバック無効
        force_slm: True なら router の判定を無視して SLM を呼ぶ (--always-slm 用)

    Returns:
        ProcessingResult
    """
    start = time.perf_counter()

    # 1. 形態素解析
    sentence = tokenize(text)

    # 2. フィラー除去 (古典 NLP)
    sentence = remove_fillers(sentence)

    # 3. 係り受け解析
    parsed = parse_dependency(sentence)

    # 4. 言い直し検出 (古典 NLP, A 型のみ)
    sentence = detect_repetition_simple(sentence, parsed)

    # 5. ルーター判定
    used_slm = False
    trigger_reason: str | None = None

    if slm_model is not None:
        if force_slm:
            used_slm = True
            trigger_reason = "force_slm"
        else:
            should_fallback, reason = needs_slm_fallback(sentence, parsed)
            if should_fallback:
                used_slm = True
                trigger_reason = reason

    # 6. SLM フォールバック実行
    slm_invoked = False
    slm_unsafe = False
    if used_slm and slm_model is not None:
        slm_invoked = True
        try:
            from pakupaku.slm import SLMUnsafeOutput, slm_repair

            sentence = slm_repair(sentence, slm_model)
        except SLMUnsafeOutput as e:
            # 安全装置が発動: SLM が内容を改変した疑い → 古典 NLP に戻す
            trigger_reason = f"{trigger_reason} (slm_unsafe: {e})"
            used_slm = False
            slm_unsafe = True
            # 古典 NLP 結果に戻すため sentence を再構築
            from pakupaku.tokenizer import tokenize as _tokenize_fn

            sentence = _tokenize_fn(text)
            sentence = remove_fillers(sentence)
            parsed = parse_dependency(sentence)
            sentence = detect_repetition_simple(sentence, parsed)
        except Exception as e:
            # その他失敗時も古典 NLP に戻す
            trigger_reason = f"{trigger_reason} (slm_failed: {e})"
            used_slm = False

    # 7. 句読点復元
    if used_slm:
        # SLM 出力をそのまま採用しつつ、文末に句点がなければ補う
        output_text = sentence.original_text.strip()
        if output_text and output_text[-1] not in {"。", "、", "！", "？", "!", "?"}:
            output_text += "。"
    else:
        output_text = restore_punctuation(sentence)

    elapsed = (time.perf_counter() - start) * 1000

    return ProcessingResult(
        input_text=text,
        output_text=output_text,
        intermediate=sentence,
        used_slm=used_slm,
        trigger_reason=trigger_reason,
        latency_ms=elapsed,
        slm_invoked=slm_invoked,
        slm_unsafe=slm_unsafe,
    )
