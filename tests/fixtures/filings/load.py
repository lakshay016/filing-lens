"""Load a zstd-compressed fixture filing by name, e.g. ``load_fixture("aapl-fy2023")``."""

from __future__ import annotations

from pathlib import Path

import zstandard

FIXTURE_DIR = Path(__file__).parent


def load_fixture(name: str) -> bytes:
    path = FIXTURE_DIR / f"{name}.htm.zst"
    return zstandard.ZstdDecompressor().decompress(
        path.read_bytes(), max_output_size=64 * 1024 * 1024
    )
