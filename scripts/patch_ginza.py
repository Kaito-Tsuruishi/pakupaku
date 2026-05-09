"""GiNZA 5.2 + spacy 3.8 + confection 1.3 互換性パッチ

問題:
    GiNZA 5.2 のモデル ja_ginza の config.cfg が `split_mode = null` を持っているが、
    新しい confection の strict 型チェックで `None != str` エラーが出てロード失敗する。

対処:
    モデル同梱の config.cfg と ginza/__init__.py の default_config を
    None → "C" (デフォルトの分割モード) に書き換える。
    GiNZA は SplitMode.C をデフォルトとしているので、動作は変わらない。

このスクリプトは `uv sync` 後に 1 回実行すれば良い。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def find_venv_site_packages() -> Path:
    """このスクリプトの venv 内 site-packages を返す"""
    here = Path(__file__).resolve()
    project_root = here.parent.parent
    candidates = [
        project_root / ".venv" / "lib" / "python3.12" / "site-packages",
        project_root / ".venv" / "lib" / "python3.13" / "site-packages",
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError("venv site-packages not found")


def patch_ginza_init(site_packages: Path) -> bool:
    """ginza/__init__.py の default_config と関数デフォルト値を修正"""
    target = site_packages / "ginza" / "__init__.py"
    if not target.exists():
        print(f"[patch_ginza] Skip: {target} not found", file=sys.stderr)
        return False

    content = target.read_text(encoding="utf-8")
    new = content

    # default_config={"split_mode": None} → {"split_mode": "C"}
    new = new.replace(
        'default_config={"split_mode": None}',
        'default_config={"split_mode": "C"}',
    )
    # split_mode: str = None → "C"
    new = re.sub(
        r"split_mode:\s*str\s*=\s*None",
        'split_mode: str = "C"',
        new,
    )

    if new == content:
        return False
    target.write_text(new, encoding="utf-8")
    print(f"[patch_ginza] patched {target}")
    return True


def patch_model_config(site_packages: Path) -> bool:
    """ja_ginza モデル同梱の config.cfg を修正"""
    candidates = list(site_packages.glob("ja_ginza/ja_ginza-*/config.cfg"))
    if not candidates:
        print("[patch_ginza] Skip: ja_ginza model config not found", file=sys.stderr)
        return False

    patched = False
    for path in candidates:
        content = path.read_text(encoding="utf-8")
        new = content.replace("split_mode = null", 'split_mode = "C"')
        if new != content:
            path.write_text(new, encoding="utf-8")
            print(f"[patch_ginza] patched {path}")
            patched = True
    return patched


def main() -> None:
    sp = find_venv_site_packages()
    p1 = patch_ginza_init(sp)
    p2 = patch_model_config(sp)
    if p1 or p2:
        print("[patch_ginza] done")
    else:
        print("[patch_ginza] no changes (already patched or up to date)")


if __name__ == "__main__":
    main()
