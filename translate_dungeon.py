"""
Translate TERA StrSheet_Dungeon floating banners (consumable tips, boss shouts).

string= bilingual [EN]/[ES], no credit. Item and monster names stay English.

Usage:
    python translate_dungeon.py source/StrSheet_Dungeon
"""

from __future__ import annotations

import argparse
from pathlib import Path

import translate_tooltips as item
import translate_string_sheet as sheet

item.SYSTEM_PROMPT = """
You are an expert video game localizer. Translate TERA MMORPG dungeon floating banners from English to Spanish.

These are red/yellow overlay lines in dungeons: consumable reminders, boon timers, boss taunts. Translate meaning naturally into Latin American Spanish.
Keep item names, monster names, place names and skill names in English: Prime Battle Solution, Bravery Potion, Noctenium Infusions, Soulcrusher, Murdranak, Lok.
Copy every __TAGn__ placeholder, HTML tag (img, font) and $token unchanged, same spelling and relative position.
GLOSSARY:
- Keep MP, HP, Battle Solution, Noctenium in English.
- Endurance is "resistencia". Never "aguante".
- Latin American Spanish: "tu", never "vosotros". Never "coger".
- Decimal comma: +1,42 not +1.42.

Do not add explanations. Do not include the English source in your output.
Translate EVERY sentence.
Return ONLY valid JSON: an array of Spanish strings, same length and order as the input array.
""".strip()

DEFAULT_CACHE = "cache/dungeon_translation_cache.json"
describe_problems = item.describe_problems
looks_untranslated = item.looks_untranslated
ATTR_RE = sheet.ATTR_RE


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Translate TERA StrSheet_Dungeon banners to bilingual EN/ES."
    )
    parser.add_argument("input_path")
    parser.add_argument("-o", "--output-dir", default="output/StrSheet_Dungeon")
    parser.add_argument("--cache", default=DEFAULT_CACHE)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--count", type=int, default=0)
    parser.add_argument("--no-ascii-entities", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return sheet.run_sheet(
        Path(args.input_path).expanduser(),
        Path(args.output_dir).expanduser(),
        Path(args.cache).expanduser(),
        "StrSheet_Dungeon-*.xml",
        args.batch_size if args.batch_size > 0 else 20,
        not args.no_ascii_entities,
        args.start,
        args.count,
    )


if __name__ == "__main__":
    raise SystemExit(main())
