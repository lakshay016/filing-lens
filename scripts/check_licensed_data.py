"""Licensed-data guard: refuse data files and CRSP-looking content in the repository.

Standard library only. Usage: python scripts/check_licensed_data.py [--staged]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

BANNED_EXTENSIONS: frozenset[str] = frozenset({".parquet", ".csv", ".sas7bdat", ".dta"})
TEXT_EXTENSIONS: frozenset[str] = frozenset(
    {".py", ".md", ".toml", ".yml", ".yaml", ".sh", ".cfg", ".ini", ".mako", ".lock"}
)
MAX_SCAN_BYTES = 20 * 1024 * 1024
# Exact repo-relative paths exempt from the rules (synthetic CRSP fixture, slice 3).
ALLOWED_PATHS: frozenset[str] = frozenset()


def _git_paths(args: list[str], repo: Path) -> list[Path]:
    out = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True).stdout
    return [Path(p.decode("utf-8", "surrogateescape")) for p in out.split(b"\0") if p]


def list_files(staged: bool, repo: Path) -> list[Path]:
    """Repo-relative paths to check: all tracked files, or only those staged."""
    if staged:
        return _git_paths(["diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"], repo)
    return _git_paths(["ls-files", "-z"], repo)


def check_file(path: Path, repo: Path) -> list[str]:
    """Reasons the file violates the guard; empty means clean."""
    if path.as_posix() in ALLOWED_PATHS:
        return []
    reasons: list[str] = []
    suffix = path.suffix.lower()
    if suffix in BANNED_EXTENSIONS:
        reasons.append(f"banned file extension {suffix}")
        return reasons
    is_data = suffix not in TEXT_EXTENSIONS and path.parts[0] != ".githooks"
    if is_data:
        full = repo / path
        if full.is_file() and not full.is_symlink():
            if full.stat().st_size > MAX_SCAN_BYTES:
                print(f"warning: skipping {path} (over 20 MB)", file=sys.stderr)
            elif b"permno" in full.read_bytes().lower():
                reasons.append("contains the string 'permno' (CRSP identifier)")
    return reasons


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true", help="check staged files only")
    args = parser.parse_args(argv)
    repo = Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    paths = list_files(args.staged, repo)
    violations = 0
    for path in paths:
        for reason in check_file(path, repo):
            print(f"LICENSED-DATA GUARD: {path.as_posix()}: {reason}")
            violations += 1
    print(f"Licensed-data guard: {len(paths)} files checked, {violations} violation(s).")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
