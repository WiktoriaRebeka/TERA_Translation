"""Shared bilingual string= rewriter for Tutorial, Dungeon and SystemMessage sheets."""

from __future__ import annotations

import re
from pathlib import Path

import translate_tooltips as item

ATTR_RE = re.compile(r'\bstring="([^"]*)"')
item.TOOLTIP_RE = re.compile(r'\bstring="([^"]*)"')

# Do not import translate_ui: that module replaces bilingual_tooltip with compact English/Spanish.
BRACE_RE = re.compile(
    r"\{@(?:select|ordinal|plural):[^{}]*\{[^{}]*\}[^{}]*\}"
    r"|\{@[A-Za-z]+(?::[^{}]+)?\}"
    r"|\{[A-Za-z+][A-Za-z0-9_]*(?:@[A-Za-z0-9_-]+)?\}"
)

item.OUTPUT_TEMPLATE = (
    "[EN] {english}"
    "&lt;br&gt;"
    "[ES] {spanish}"
)

item.MARKUP_RE = re.compile(
    item.TAG_RE.pattern
    + "|"
    + item.VAR_RE.pattern
    + "|"
    + item.LINK_RE.pattern
    + "|"
    + BRACE_RE.pattern
    + r"|\x01"
)

# Optional: leave instance titles / numerals in English (Dungeon 00000 names).
LEAVE_ENGLISH_FN = None


def to_tera_html_entities(text: str) -> str:
    return "".join(c if ord(c) < 128 else f"&amp;#{ord(c)};" for c in text)


item.to_ascii_entities = to_tera_html_entities


def collect_unique_uncached(lines: list[str], cache: dict[str, str]) -> list[str]:
    unique: list[str] = []
    seen = set(cache.keys())
    for line in lines:
        for match in ATTR_RE.finditer(line):
            original = match.group(1)
            if original == "" or original in seen:
                continue
            if LEAVE_ENGLISH_FN and LEAVE_ENGLISH_FN(original):
                continue
            if item.is_already_bilingual(original):
                continue
            seen.add(original)
            unique.append(original)
    return unique


def rewrite_lines(
    lines: list[str],
    cache: dict[str, str],
    ascii_safe: bool = True,
) -> tuple[list[str], dict[str, int]]:
    output_lines: list[str] = []
    stats = {
        "applied": 0,
        "already_bilingual": 0,
        "empty": 0,
        "no_tooltip": 0,
        "left_original": 0,
    }
    for line in lines:
        matches = list(ATTR_RE.finditer(line))
        if not matches:
            output_lines.append(line)
            stats["no_tooltip"] += 1
            continue
        new_line = line
        for match in reversed(matches):
            original = match.group(1)
            if original == "":
                stats["empty"] += 1
                continue
            if LEAVE_ENGLISH_FN and LEAVE_ENGLISH_FN(original):
                stats["left_original"] += 1
                continue
            if item.is_already_bilingual(original):
                stats["already_bilingual"] += 1
                continue
            spanish_escaped = cache.get(original)
            if spanish_escaped is None:
                stats["left_original"] += 1
                continue
            start, end = match.span(1)
            new_value = item.bilingual_tooltip(original, spanish_escaped)
            new_line = new_line[:start] + new_value + new_line[end:]
            stats["applied"] += 1
        output_lines.append(new_line)
    if ascii_safe:
        output_lines = [item.ascii_safe_line(line) for line in output_lines]
    return output_lines, stats


item.collect_unique_uncached = collect_unique_uncached
item.rewrite_lines = rewrite_lines


def list_sheet_files(root: Path, glob_pat: str, start: int, count: int) -> list[Path]:
    files = sorted(root.glob(glob_pat))
    if start < 0:
        start = 0
    files = files[start:]
    if count > 0:
        files = files[:count]
    return files


def run_sheet(
    input_path: Path,
    output_dir: Path,
    cache_path: Path,
    glob_pat: str,
    batch_size: int,
    ascii_safe: bool,
    start: int,
    count: int,
) -> int:
    if input_path.is_file():
        files = [input_path]
    elif input_path.is_dir():
        files = list_sheet_files(input_path, glob_pat, start, count)
        if not files:
            print(f"No {glob_pat} in {input_path}")
            return 1
        print(f"Pack: {files[0].name} .. {files[-1].name} ({len(files)} files)", flush=True)
    else:
        print(f"Input not found: {input_path}")
        return 1
    item.process_files(files, output_dir, cache_path, batch_size, ascii_safe)
    return 0
