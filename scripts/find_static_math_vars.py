#!/usr/bin/env python3
"""Find static math constants in extracted assembly.

This script scans assembly files to:
1) discover symbols loaded by floating-point load instructions (lfs/lfd), and
2) resolve those symbols to data definitions in .sdata2/.rodata-like sections.

The output is a text report of candidate static mathematical variables.
"""

from __future__ import annotations

import argparse
import math
import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

FP_LOAD_RE = re.compile(
    r"\b(?:lfs|lfd)\s+f\d+\s*,\s*([A-Za-z_.$][\w.$]*)(?:@\w+)?(?:\(r\d+\))?"
)
LABEL_RE = re.compile(r"^\s*([A-Za-z_.$][\w.$]*):")
SECTION_RE = re.compile(r"^\s*\.section\s+([^,\s]+)")

FLOAT_RE = re.compile(r"^\s*\.float\s+([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)")
DOUBLE_RE = re.compile(r"^\s*\.double\s+([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)")
WORD_RE = re.compile(r"^\s*\.4byte\s+([^\s#]+)")
DWORD_RE = re.compile(r"^\s*\.8byte\s+([^\s#]+)")

DATA_SECTIONS = {
    ".sdata2",
    ".rodata",
    ".rdata",
    ".lit4",
    ".lit8",
}


@dataclass
class ConstantInfo:
    section: str
    source: Path
    kind: str
    value: float


def asm_files(asm_dir: Path) -> Iterable[Path]:
    for ext in ("*.s", "*.S", "*.asm"):
        yield from asm_dir.rglob(ext)


def parse_int_literal(raw: str) -> Optional[int]:
    raw = raw.rstrip(",")
    try:
        if raw.lower().startswith("0x"):
            return int(raw, 16)
        return int(raw, 10)
    except ValueError:
        return None


def decode_f32(word: int) -> float:
    return struct.unpack(">f", struct.pack(">I", word & 0xFFFFFFFF))[0]


def decode_f64(dword: int) -> float:
    return struct.unpack(">d", struct.pack(">Q", dword & 0xFFFFFFFFFFFFFFFF))[0]


def discover_fp_refs(paths: Iterable[Path]) -> Set[str]:
    refs: Set[str] = set()
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line in text.splitlines():
            match = FP_LOAD_RE.search(line)
            if match:
                refs.add(match.group(1))
    return refs


def discover_constant_defs(paths: Iterable[Path]) -> Dict[str, ConstantInfo]:
    constants: Dict[str, ConstantInfo] = {}

    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue

        section = ""
        current_label: Optional[str] = None

        for line in lines:
            sec = SECTION_RE.match(line)
            if sec:
                section = sec.group(1)
                current_label = None
                continue

            label = LABEL_RE.match(line)
            if label:
                current_label = label.group(1)
                continue

            if not current_label or section not in DATA_SECTIONS:
                continue

            f_match = FLOAT_RE.match(line)
            if f_match:
                value = float(f_match.group(1))
                constants.setdefault(
                    current_label,
                    ConstantInfo(section=section, source=path, kind="float", value=value),
                )
                current_label = None
                continue

            d_match = DOUBLE_RE.match(line)
            if d_match:
                value = float(d_match.group(1))
                constants.setdefault(
                    current_label,
                    ConstantInfo(section=section, source=path, kind="double", value=value),
                )
                current_label = None
                continue

            w_match = WORD_RE.match(line)
            if w_match:
                value_int = parse_int_literal(w_match.group(1))
                if value_int is not None:
                    value = decode_f32(value_int)
                    if math.isfinite(value):
                        constants.setdefault(
                            current_label,
                            ConstantInfo(
                                section=section,
                                source=path,
                                kind="float(4byte)",
                                value=value,
                            ),
                        )
                        current_label = None
                continue

            dw_match = DWORD_RE.match(line)
            if dw_match:
                value_int = parse_int_literal(dw_match.group(1))
                if value_int is not None:
                    value = decode_f64(value_int)
                    if math.isfinite(value):
                        constants.setdefault(
                            current_label,
                            ConstantInfo(
                                section=section,
                                source=path,
                                kind="double(8byte)",
                                value=value,
                            ),
                        )
                        current_label = None

    return constants


def format_report(refs: Set[str], constants: Dict[str, ConstantInfo]) -> List[str]:
    matched = []
    for sym in sorted(refs):
        info = constants.get(sym)
        if info is None:
            continue
        matched.append((sym, info))

    lines: List[str] = []
    lines.append("# Static mathematical variable candidates")
    lines.append(f"# referenced floating-point symbols: {len(refs)}")
    lines.append(f"# resolved constants: {len(matched)}")
    lines.append("")

    for sym, info in matched:
        lines.append(
            f"{sym} = {info.value:.17g} [{info.kind}] ({info.section}) @ {info.source.as_posix()}"
        )

    if not matched:
        lines.append("No matching constants were found.")

    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asm-dir", type=Path, default=Path("asm"), help="Assembly root")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("build/static_math_vars.txt"),
        help="Output report file",
    )
    args = parser.parse_args()

    if not args.asm_dir.exists():
        print(f"warning: asm directory does not exist: {args.asm_dir}")
        return 0

    paths = list(asm_files(args.asm_dir))
    refs = discover_fp_refs(paths)
    constants = discover_constant_defs(paths)

    report = format_report(refs, constants)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"Wrote {args.output} ({len(report)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
