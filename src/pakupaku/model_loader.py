"""SLM / STT モデルの DL とロードを管理する"""

from __future__ import annotations

from pathlib import Path

from pakupaku.config import (
    ADAPTERS_DIR,
    CACHE_DIR,
    DEFAULT_SLM_MODEL,
    DEFAULT_STT_MODEL,
)


def _ensure_cached(repo_id: str) -> Path:
    """HF Hub からモデルを DL してローカルパスを返す (キャッシュ済みならスキップ)"""
    from huggingface_hub import snapshot_download

    local_dir = CACHE_DIR / repo_id.replace("/", "__")
    if not local_dir.exists():
        local_dir.mkdir(parents=True, exist_ok=True)
        print(f"[pakupaku] Downloading {repo_id} to {local_dir} ...")
        snapshot_download(repo_id=repo_id, local_dir=str(local_dir))
    return local_dir


def get_slm(adapter_version: str | None = None):
    """SLM をロードして (model, processor) を返す

    Gemma 4 はマルチモーダル前提のため mlx-vlm 経由で読み込む。
    pakupaku はテキストのみ生成するため画像・音声入力は使わない。

    Args:
        adapter_version: LoRA アダプターのディレクトリ名 (例: "v1")。
                         融合済みのモデルが事前に用意されていれば使う (Phase 6)。
    """
    from mlx_vlm import load

    base_path = _ensure_cached(DEFAULT_SLM_MODEL)

    if adapter_version is None:
        return load(str(base_path))

    fused_path = ADAPTERS_DIR / adapter_version / "fused"
    if fused_path.exists():
        return load(str(fused_path))

    raise FileNotFoundError(
        f"Fused adapter not found at {fused_path}. "
        f"Run fuse step first (Phase 6)."
    )


def get_whisper_path() -> Path:
    """Whisper モデルをローカルキャッシュに DL してパスを返す"""
    return _ensure_cached(DEFAULT_STT_MODEL)
