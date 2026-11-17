from __future__ import annotations

import hashlib
from pathlib import Path

from filinglens.edgar.store import raw_path, read_raw, write_raw


def test_raw_path(tmp_path: Path) -> None:
    p = raw_path(tmp_path, 320193, "0000320193-23-000106", "aapl.htm")
    assert p == tmp_path / "raw" / "320193" / "0000320193-23-000106" / "aapl.htm.zst"


def test_round_trip_and_hash(tmp_path: Path) -> None:
    content = b"<html>" + b"hello world " * 1000 + b"</html>"
    p = raw_path(tmp_path, 1, "0000000001-23-000001", "x.htm")
    sha, size = write_raw(p, content)
    assert sha == hashlib.sha256(content).hexdigest()  # of the uncompressed bytes
    assert size == len(content)
    assert p.stat().st_size < len(content)  # actually compressed
    assert read_raw(p) == content


def test_no_temporary_file_left(tmp_path: Path) -> None:
    p = raw_path(tmp_path, 1, "0000000001-23-000001", "x.htm")
    write_raw(p, b"one")
    write_raw(p, b"two")  # overwrite
    assert [f.name for f in p.parent.iterdir()] == ["x.htm.zst"]
    assert read_raw(p) == b"two"
