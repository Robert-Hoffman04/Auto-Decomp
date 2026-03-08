#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <GAMEID>"
  echo "Example: $0 GLZE01"
  exit 1
fi

GAMEID="${1^^}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"

if [[ ! -d "config/$GAMEID" ]]; then
  echo "error: config/$GAMEID does not exist"
  echo "Run scripts/setup_project.sh $GAMEID first."
  exit 1
fi

if [[ ! -d "orig/$GAMEID" ]]; then
  echo "error: orig/$GAMEID does not exist"
  exit 1
fi

echo "[1/3] Generating build files for $GAMEID"
python3 configure.py --version "$GAMEID"

echo "[2/3] Running initial analysis/build"
ninja

echo "[3/3] Scanning asm for static mathematical variables"
python3 scripts/find_static_math_vars.py --asm-dir asm --output "build/$GAMEID/static_math_vars.txt"


echo "Done. Check generated files in config/$GAMEID and build/$GAMEID"
