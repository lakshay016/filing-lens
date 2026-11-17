"""Raw filing storage: zstd-compressed primary documents under ``data/raw`` (SPEC §5.2)."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

import zstandard

_LEVEL = 10


def raw_path(data_dir: Path, cik: int, accession: str, primary_document: str) -> Path:
    return data_dir / "raw" / str(cik) / accession / (primary_document + ".zst")


def write_raw(path: Path, content: bytes) -> tuple[str, int]:
    """Write atomically; return (sha256 hex of the uncompressed bytes, length)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    compressed = zstandard.ZstdCompressor(level=_LEVEL).compress(content)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(compressed)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return hashlib.sha256(content).hexdigest(), len(content)


def read_raw(path: Path) -> bytes:
    return zstandard.ZstdDecompressor().decompress(path.read_bytes(), max_output_size=1 << 31)
