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

# Rename template directories.
if [[ -d "config/GAMEID" && ! -d "config/$GAMEID" ]]; then
  mv "config/GAMEID" "config/$GAMEID"
fi
if [[ -d "orig/GAMEID" && ! -d "orig/$GAMEID" ]]; then
  mv "orig/GAMEID" "orig/$GAMEID"
fi

if [[ ! -d "orig/$GAMEID" ]]; then
  mkdir -p "orig/$GAMEID"
fi

python3 - "$GAMEID" <<'PY'
from pathlib import Path
import hashlib
import re
import sys

root = Path.cwd()
gameid = sys.argv[1]
orig_dir = root / "orig" / gameid
config_dir = root / "config" / gameid
config_path = config_dir / "config.yml"
build_sha_path = config_dir / "build.sha1"


def sha1(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def replace_versions(configure_text: str) -> str:
    return re.sub(
        r'VERSIONS = \[\n\s*"GAMEID",\s*# 0\n\]',
        f'VERSIONS = [\n    "{gameid}",  # 0\n]',
        configure_text,
    )


# Update configure.py version list.
configure = root / "configure.py"
if configure.exists():
    ctext = configure.read_text(encoding="utf-8")
    configure.write_text(replace_versions(ctext), encoding="utf-8")

# Update README placeholder references.
readme = root / "README.md"
if readme.exists():
    rtext = readme.read_text(encoding="utf-8")
    readme.write_text(rtext.replace("[GAMEID]", gameid), encoding="utf-8")

if not config_path.exists():
    print(f"warning: {config_path} not found, skipping config auto-population")
    raise SystemExit(0)

cfg = config_path.read_text(encoding="utf-8")
cfg = cfg.replace("GAMEID", gameid)

main_dol = orig_dir / "sys" / "main.dol"
if main_dol.exists():
    cfg = re.sub(r"(?m)^hash:\s*[0-9a-f]{40}$", f"hash: {sha1(main_dol)}", cfg, count=1)

# Detect REL modules in orig/<GAMEID>/files/*.rel and build modules block.
modules_dir = orig_dir / "files"
rels = sorted(modules_dir.glob("*.rel")) if modules_dir.exists() else []
if rels:
    module_lines = ["modules:"]
    for rel in rels:
        module_name = rel.stem
        rel_hash = sha1(rel)
        module_lines.extend(
            [
                f"- object: files/{rel.name}",
                f"  hash: {rel_hash}",
                f"  symbols: config/{gameid}/{module_name}/symbols.txt",
                f"  splits: config/{gameid}/{module_name}/splits.txt",
                "",
            ]
        )
    module_block = "\n".join(module_lines).rstrip() + "\n"
    cfg = re.sub(r"(?ms)^modules:\n- object:.*\Z", module_block, cfg)

# Optional Wii selfile hash auto-fill.
selfile = orig_dir / "files" / "selfile.sel"
if selfile.exists() and "selfile_hash:" in cfg:
    cfg = re.sub(r"(?m)^selfile_hash:\s*[0-9a-f]{40}$", f"selfile_hash: {sha1(selfile)}", cfg)

config_path.write_text(cfg, encoding="utf-8")

# Populate build.sha1 when possible.
entries = []
if main_dol.exists():
    entries.append((sha1(main_dol), f"build/{gameid}/main.dol"))
for rel in rels:
    module_name = rel.stem
    entries.append((sha1(rel), f"build/{gameid}/{module_name}/{module_name}.rel"))
if entries:
    lines = [f"{digest}  {path}" for digest, path in entries]
    build_sha_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

print(f"Auto-populated config for {gameid}.")
if main_dol.exists():
    print("  - main.dol hash set")
if rels:
    print(f"  - detected {len(rels)} REL module(s)")
if entries:
    print("  - build.sha1 regenerated")
PY

echo "Project scaffold configured for $GAMEID"
echo "Next steps:"
echo "  1) Review config/$GAMEID/config.yml"
echo "  2) Run scripts/initial_run.sh $GAMEID"
