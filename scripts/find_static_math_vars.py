#!/usr/bin/env python3
"""Find static math constants in extracted assembly and optionally apply them to symbols.txt."""

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
OBJ_RE = re.compile(r"^\s*\.obj\s+([A-Za-z_.$][\w.$]*)\s*,")
ENDOBJ_RE = re.compile(r"^\s*\.endobj\b")
SECTION_RE = re.compile(r"^\s*\.section\s+([^,\s]+)")
SECTION_COMMENT_RE = re.compile(r"^\s*#\s*(\.[A-Za-z0-9_.$]+):")

FLOAT_RE = re.compile(r"^\s*\.float\s+([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)")
DOUBLE_RE = re.compile(r"^\s*\.double\s+([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)")
WORD_RE = re.compile(r"^\s*\.4byte\s+([^\s#]+)")
DWORD_RE = re.compile(r"^\s*\.8byte\s+([^\s#]+)")

SYMBOL_LINE_RE = re.compile(r"^\s*([A-Za-z_.$][\w.$]*)\s*=")
ADDR_IN_NAME_RE = re.compile(r"(?:^|_)([0-9A-Fa-f]{6,16})$")

DATA_SECTIONS = {".sdata2", ".rodata", ".rdata", ".lit4", ".lit8"}


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


def parse_addr_from_symbol_name(symbol: str) -> Optional[int]:
    match = ADDR_IN_NAME_RE.search(symbol)
    if not match:
        return None
    try:
        return int(match.group(1), 16)
    except ValueError:
        return None


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

            sec_comment = SECTION_COMMENT_RE.match(line)
            if sec_comment:
                section = sec_comment.group(1)
                current_label = None
                continue

            label = LABEL_RE.match(line)
            if label:
                current_label = label.group(1)
                continue

            obj = OBJ_RE.match(line)
            if obj:
                current_label = obj.group(1)
                continue

            if ENDOBJ_RE.match(line):
                current_label = None
                continue

            if not current_label or section not in DATA_SECTIONS:
                continue

            f_match = FLOAT_RE.match(line)
            if f_match:
                constants.setdefault(
                    current_label,
                    ConstantInfo(section=section, source=path, kind="float", value=float(f_match.group(1))),
                )
                current_label = None
                continue

            d_match = DOUBLE_RE.match(line)
            if d_match:
                constants.setdefault(
                    current_label,
                    ConstantInfo(section=section, source=path, kind="double", value=float(d_match.group(1))),
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
                            ConstantInfo(section=section, source=path, kind="float(4byte)", value=value),
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
                            ConstantInfo(section=section, source=path, kind="double(8byte)", value=value),
                        )
                        current_label = None

    return constants


def format_report(refs: Set[str], constants: Dict[str, ConstantInfo]) -> List[str]:
    matched = []
    for sym in sorted(refs):
        info = constants.get(sym)
        if info is not None:
            matched.append((sym, info))

    lines: List[str] = [
        "# Static mathematical variable candidates",
        f"# referenced floating-point symbols: {len(refs)}",
        f"# resolved constants: {len(matched)}",
        "",
    ]

    for sym, info in matched:
        lines.append(
            f"{sym} = {info.value:.17g} [{info.kind}] ({info.section}) @ {info.source.as_posix()}"
        )

    if not matched:
        lines.append("No matching constants were found.")

    return lines


def parse_existing_symbols(symbols_path: Path) -> Set[str]:
    if not symbols_path.exists():
        return set()
    names: Set[str] = set()
    for line in symbols_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = SYMBOL_LINE_RE.match(line)
        if m:
            names.add(m.group(1))
    return names


def build_symbol_line(name: str, info: ConstantInfo, addr: int) -> str:
    data_attr = "double" if "double" in info.kind else "float"
    return (
        f"{name} = {info.section}:0x{addr:X}; "
        f"// type:object data:{data_attr} autogenerated:static_math_var"
    )


def apply_to_symbols(symbols_path: Path, refs: Set[str], constants: Dict[str, ConstantInfo]) -> int:
    existing = parse_existing_symbols(symbols_path)
    additions: List[str] = []

    for sym in sorted(refs):
        if sym in existing:
            continue
        info = constants.get(sym)
        if info is None:
            continue
        addr = parse_addr_from_symbol_name(sym)
        if addr is None:
            continue
        additions.append(build_symbol_line(sym, info, addr))

    if not additions:
        return 0

    symbols_path.parent.mkdir(parents=True, exist_ok=True)
    with symbols_path.open("a", encoding="utf-8") as f:
        if symbols_path.stat().st_size > 0:
            f.write("\n")
        f.write("\n".join(additions))
        f.write("\n")

    return len(additions)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asm-dir", type=Path, default=Path("asm"), help="Assembly root")
    parser.add_argument("--output", type=Path, default=Path("build/static_math_vars.txt"), help="Output report file")
    parser.add_argument("--symbols", type=Path, help="If set, append discovered static math symbols to this symbols.txt")
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

    if args.symbols:
        added = apply_to_symbols(args.symbols, refs, constants)
        print(f"Updated {args.symbols}: added {added} symbol(s)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
