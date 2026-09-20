"""
Translate TERA StrSheet_SystemMessage combat chat and system popups.

string= bilingual [EN]/[ES], no credit. Copy {UserName}, {@select:}, {Amount@money}
verbatim. Item, skill, place and class names stay English. HP/MP stay English.

Usage:
    python translate_systemmessage.py source/StrSheet_SystemMessage
"""

from __future__ import annotations

import argparse
from pathlib import Path

import translate_tooltips as item
import translate_string_sheet as sheet

item.SYSTEM_PROMPT = """
You are an expert video game localizer. Translate TERA MMORPG system messages from English to Spanish.

These appear in combat chat, party/guild chat, error toasts and confirmation popups. Translate meaning naturally into Latin American Spanish. Keep the terse system-message tone.
Keep item names, skill names, place names, dungeon names, class names and key names in English.
Copy every brace token unchanged, same spelling and relative position: {UserName}, {QuestName}, {itemName}, {Key}, {Amount@money}, {goldAmount@money}, {@select:{itemNumber}/s//s}, {@ordinal:{lordNumber}}, {@money:100000000}, {+number}. Never invent extra tokens. Never translate the inside of a {token}.
Copy every __TAGn__ placeholder, HTML tag (font, br) and $token unchanged.
GLOSSARY:
- Keep MP, HP in English. Never PM, PH, mana, PV, PS.
- Endurance is "resistencia". Never "aguante".
- Latin American Spanish: "tu", never "vosotros". Never "coger".
- Decimal comma: +1,42 not +1.42.

Do not add explanations. Do not include the English source in your output.
Translate EVERY sentence.
Return ONLY valid JSON: an array of Spanish strings, same length and order as the input array.
""".strip()

DEFAULT_CACHE = "cache/systemmessage_translation_cache.json"
describe_problems = item.describe_problems
looks_untranslated = item.looks_untranslated
ATTR_RE = sheet.ATTR_RE
BRACE_RE = sheet.BRACE_RE


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Translate TERA StrSheet_SystemMessage chat to bilingual EN/ES."
    )
    parser.add_argument("input_path")
    parser.add_argument("-o", "--output-dir", default="output/StrSheet_SystemMessage")
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
        "StrSheet_SystemMessage-*.xml",
        args.batch_size if args.batch_size > 0 else 20,
        not args.no_ascii_entities,
        args.start,
        args.count,
    )


if __name__ == "__main__":
    raise SystemExit(main())
