"""
Translate TERA StrSheet_Npc menu labels (Learn Skills, Expand Inventory, shops).

Same compact English/Spanish format as UI. Unicode accents (hash is color).
NPC / item / place names stay English.

Usage:
    python translate_npc.py source/StrSheet_Npc
    python translate_npc.py source/StrSheet_Npc/StrSheet_Npc-00000.xml
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import translate_tooltips as item
import translate_ui as ui

item.TOOLTIP_RE = re.compile(r'string="([^"]*)"')
item.collect_unique_uncached = ui.collect_unique_uncached
item.bilingual_tooltip = ui.ui_string
item.to_ascii_entities = ui.to_tera_html_entities
item.to_tera_html_entities = ui.to_tera_html_entities

item.SYSTEM_PROMPT = """
You are an expert video game localizer. Translate TERA MMORPG NPC menu labels from English to Spanish.

These are the short buttons a player sees when talking to an NPC: Learn Skills, Expand Inventory, Shop, Bank, Create Guild, Travel. Translate the visible meaning into natural Latin American Spanish. Return ONLY the Spanish text - the local script prepends the English source as Learn Skills/Aprender habilidades.

Keep NPC names, item names, place names, dungeon names, class names and race names in English.
Keyboard key names stay in English.
Preserve numbers and punctuation.
Placeholders like __TAG0__ must be copied unchanged.
GLOSSARY:
- Keep MP, HP in English. Never PM, PH, mana, PV, PS.
- Endurance is "resistencia". Never "aguante".
- Latin American Spanish: "tu", never "vosotros". Never "coger".
- Decimal comma: +1,42 not +1.42.

Do not add explanations. Do not include the English source in your output.
Return ONLY valid JSON: an array of Spanish strings, same length and order as the input array.
""".strip()

DEFAULT_CACHE = "cache/npc_translation_cache.json"
CREDIT = item.CREDIT
FORBIDDEN_ES = ui.FORBIDDEN_ES
KEEP_ENGLISH = item.KEEP_ENGLISH
ORPHAN_TAG_RE = item.ORPHAN_TAG_RE
TOOLTIP_RE = item.TOOLTIP_RE
describe_problems = item.describe_problems
engine_vars = item.engine_vars
looks_untranslated = item.looks_untranslated
should_leave_english = ui.should_leave_english
split_ui_pair = ui.split_ui_pair


def list_npc_files(root: Path, start: int, count: int) -> list[Path]:
    files = sorted(root.glob("StrSheet_Npc-*.xml"))
    if start < 0:
        start = 0
    files = files[start:]
    if count > 0:
        files = files[:count]
    return files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Translate TERA StrSheet_Npc menu labels to compact EN/ES."
    )
    parser.add_argument("input_path", help="Folder with StrSheet_Npc-*.xml, or one XML file")
    parser.add_argument(
        "-o",
        "--output-dir",
        default="output/StrSheet_Npc",
        help="Folder na przetlumaczone XML",
    )
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
        files = list_npc_files(input_path, args.start, args.count)
        if not files:
            print(f"No StrSheet_Npc XML in {input_path}", file=sys.stderr)
            return 1
        print(f"Pack: {files[0].name} .. {files[-1].name} ({len(files)} files)", flush=True)
    else:
        print(f"Input not found: {input_path}", file=sys.stderr)
        return 1

    item.process_files(files, output_dir, cache_path, batch_size, ascii_safe)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
