"""
Translate TERA StrSheet_Passivity green gear lines (name=) and extra tooltips.

Bilingual [EN]/[ES] without Transcription credit. Skill names stay English.
$name and tooltip= can sit on the same XML line.

Usage:
    python translate_passivity.py source/StrSheet_Passivity
    python translate_passivity.py source/StrSheet_Passivity/StrSheet_Passivity-00000.xml
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

import translate_tooltips as item

ATTR_RE = re.compile(r'\b(name|tooltip)="([^"]*)"')
item.TOOLTIP_RE = re.compile(r'\b(?:name|tooltip)="([^"]*)"')

item.OUTPUT_TEMPLATE = (
    "[EN] {english}"
    "&lt;br&gt;"
    "[ES] {spanish}"
)


def to_tera_html_entities(text: str) -> str:
    return "".join(c if ord(c) < 128 else f"&amp;#{ord(c)};" for c in text)


item.to_ascii_entities = to_tera_html_entities

# BHS leftover names (Equipment_Weapon_Normal_Absorbs damage9, T3_Mystic,
# IncreaseMaxMP78). Not player-facing green text; sending them to Gemini
# makes the model invent $value and the whole batch gets rejected.
_DEV_STRIP_RE = re.compile(r"<[^>]+>")
_DEV_CAMEL_RE = re.compile(r"[a-z][A-Z]")


def is_dev_leftover(text: str) -> bool:
    stripped = item.VAR_RE.sub(" ", html.unescape(text))
    stripped = _DEV_STRIP_RE.sub(" ", stripped)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    if "_" in stripped or re.search(r"damage\d+\s*$", stripped, re.I):
        return True
    if " " not in stripped and _DEV_CAMEL_RE.search(stripped):
        return True
    return False


def collect_unique_uncached(lines: list[str], cache: dict[str, str]) -> list[str]:
    unique: list[str] = []
    seen = set(cache.keys())
    for line in lines:
        for match in ATTR_RE.finditer(line):
            original = match.group(2)
            if original == "" or original in seen:
                continue
            if item.is_already_bilingual(original) or is_dev_leftover(original):
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
            original = match.group(2)
            if original == "":
                stats["empty"] += 1
                continue
            if item.is_already_bilingual(original):
                stats["already_bilingual"] += 1
                continue
            if is_dev_leftover(original):
                stats["left_original"] += 1
                continue
            spanish_escaped = cache.get(original)
            if spanish_escaped is None:
                stats["left_original"] += 1
                continue
            start, end = match.span(2)
            new_value = item.bilingual_tooltip(original, spanish_escaped)
            new_line = new_line[:start] + new_value + new_line[end:]
            stats["applied"] += 1
        output_lines.append(new_line)
    if ascii_safe:
        output_lines = [item.ascii_safe_line(line) for line in output_lines]
    return output_lines, stats


item.collect_unique_uncached = collect_unique_uncached
item.rewrite_lines = rewrite_lines

item.SYSTEM_PROMPT = """
You are an expert video game localizer. Translate TERA MMORPG item bonus lines from English to Spanish.

These are short green lines on gear and crystal effects, for example: "Decreases damage from enraged monsters.", "Raises your max HP."
Translate meaning naturally into Latin American Spanish. Keep the combat tone of TERA.
Skill names, buff names, etching names and crystal option names stay English: Stand Fast, Poison VII, Cruelty VII, Forcefulness VII, Kaia's Fury, Grounded, Relentless, Etching.
Class names stay English. Monster type words that are proper names stay English.
Copy every __TAGn__ placeholder and every $token that already appears in that source string, in the same relative position. Never invent extra tokens. If the source has no $value / $BR / $COLOR_END / $H_W_GOOD / $H_S_GOOD, the Spanish must not contain any either.
GLOSSARY:
- Keep MP, HP, Etching in English. Never PM, PH, mana, PV, PS.
- Endurance is "resistencia". Never "aguante".
- Power is "poder". Crit Power is "poder de golpe critico".
- The English multiplier word "times" becomes "veces".
- Latin American Spanish: "tu", never "vosotros". Never "coger".
- Decimal comma: +1,42 not +1.42.

Do not add explanations. Do not include the English source in your output.
Return ONLY valid JSON: an array of Spanish strings, same length and order as the input array.
""".strip()

DEFAULT_CACHE = "cache/passivity_translation_cache.json"
CREDIT = item.CREDIT
FORBIDDEN_ES = item.FORBIDDEN_ES
KEEP_ENGLISH = item.KEEP_ENGLISH
ORPHAN_TAG_RE = item.ORPHAN_TAG_RE
TOOLTIP_RE = item.TOOLTIP_RE
describe_problems = item.describe_problems
engine_vars = item.engine_vars
looks_untranslated = item.looks_untranslated


def list_files(root: Path, start: int, count: int) -> list[Path]:
    files = sorted(root.glob("StrSheet_Passivity-*.xml"))
    if start < 0:
        start = 0
    files = files[start:]
    if count > 0:
        files = files[:count]
    return files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Translate TERA StrSheet_Passivity green lines to bilingual EN/ES."
    )
    parser.add_argument("input_path")
    parser.add_argument("-o", "--output-dir", default="output/StrSheet_Passivity")
    parser.add_argument("--cache", default=DEFAULT_CACHE)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--count", type=int, default=0)
    parser.add_argument("--no-ascii-entities", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input_path).expanduser()
    output_dir = Path(args.output_dir).expanduser()
    cache_path = Path(args.cache).expanduser()
    batch_size = args.batch_size if args.batch_size > 0 else 20
    ascii_safe = not args.no_ascii_entities

    if input_path.is_file():
        files = [input_path]
    elif input_path.is_dir():
        files = list_files(input_path, args.start, args.count)
        if not files:
            print(f"No StrSheet_Passivity XML in {input_path}", file=sys.stderr)
            return 1
        print(f"Pack: {files[0].name} .. {files[-1].name} ({len(files)} files)", flush=True)
    else:
        print(f"Input not found: {input_path}", file=sys.stderr)
        return 1

    item.process_files(files, output_dir, cache_path, batch_size, ascii_safe)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
