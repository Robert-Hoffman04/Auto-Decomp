#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <GAMEID>"
  echo "Example: $0 GLZE01"
  exit 1
fi

GAMEID="${1^^}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ! "$GAMEID" =~ ^[A-Z0-9]{6}$ ]]; then
  echo "error: GAMEID must be a 6-character disc ID (letters/numbers), got '$GAMEID'"
  exit 1
fi

cd "$ROOT_DIR"

if [[ -d "config/GAMEID" ]]; then
  mv "config/GAMEID" "config/$GAMEID"
fi
if [[ -d "orig/GAMEID" ]]; then
  mv "orig/GAMEID" "orig/$GAMEID"
fi

python3 - "$GAMEID" <<'PY'
from pathlib import Path
import re
import sys

root = Path.cwd()
gameid = sys.argv[1]

configure = root / "configure.py"
text = configure.read_text(encoding="utf-8")
text = re.sub(
    r'VERSIONS = \[\n\s*"GAMEID",\s*# 0\n\]',
    f'VERSIONS = [\n    "{gameid}",  # 0\n]',
    text,
)
configure.write_text(text, encoding="utf-8")

readme = root / "README.md"
if readme.exists():
    content = readme.read_text(encoding="utf-8")
    content = content.replace("[GAMEID]", gameid)
    readme.write_text(content, encoding="utf-8")
PY

echo "Project scaffold configured for $GAMEID"
echo "Next steps:"
echo "  1) Put your game image or extracted files into orig/$GAMEID"
echo "  2) Edit config/$GAMEID/config.yml"
echo "  3) Run scripts/initial_run.sh $GAMEID"
