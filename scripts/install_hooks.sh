#!/bin/sh
# Point git at the repository's hooks directory (local config only).
set -e
git config core.hooksPath .githooks
echo "Set core.hooksPath to .githooks (pre-commit runs the licensed-data guard)."
