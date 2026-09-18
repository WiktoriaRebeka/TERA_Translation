"""
Translate TERA StrSheet_Quest strings (titles, journal text, NPC quest lines)
to bilingual EN/ES via the same Gemini pipeline as items.

Quest XML uses id= + string= (no toolTip). Hundreds of tiny files share
repeated lines, so this script translates a whole folder in one Gemini run
on a shared cache.

Usage:
    python translate_quest.py source/StrSheet_Quest
    python translate_quest.py source/StrSheet_Quest --start 0 --count 50
    python translate_quest.py source/StrSheet_Quest/StrSheet_Quest-00000.xml
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import translate_tooltips as item

item.TOOLTIP_RE = re.compile(r'string="([^"]*)"')

QUEST_SKIP_EXACT = {
    "idle1",
    "idle2",
    "idle3",
    "talk1",
    "talk2",
    "talk3",
    "victory",
    "applaud",
    "request",
    "worry",
    "shy",
    "angry",
    "sob",
    "greet",
    "taunt",
    "propose",
    "attack",
    "pointing",
    "dance",
    "smile",
}


def should_leave_english(original: str) -> bool:
    text = original.strip()
    return text in QUEST_SKIP_EXACT


_orig_collect = item.collect_unique_uncached


def collect_unique_uncached(lines: list[str], cache: dict[str, str]) -> list[str]:
    unique = _orig_collect(lines, cache)
    return [text for text in unique if not should_leave_english(text)]


item.collect_unique_uncached = collect_unique_uncached


def to_tera_html_entities(text: str) -> str:
    return "".join(c if ord(c) < 128 else f"&amp;#{ord(c)};" for c in text)


item.to_ascii_entities = to_tera_html_entities

item.SYSTEM_PROMPT = """
You are an expert video game localizer. Translate TERA MMORPG quest text from English to Spanish.

These strings are quest titles, journal summaries, objectives and short NPC lines from the quest flow. Translate meaning naturally into Latin American Spanish. Keep the tone of high fantasy TERA.
Keep proper names (Kelsaik, Valkyon, Bahaar, Kaia, Elin, Velika, Allemantheia, Kaiator, Acarum, Elenea, Bloody Depths, Roostcliff Quarter, World Tree, Tower of Shara, Zolyn, Alyssa, Slevene, etc.) unchanged unless a well-known Spanish TERA name already exists.
Quest titles are translated, but place names and NPC names stay in English.
Class and race names used as labels stay in English: Warrior, Lancer, Elin, Castanic, Popori, Baraka, Amani.
Anything inside square brackets is copied in English exactly as written, except known headings the local script will swap.
Preserve numbers, punctuation and placeholders like __TAG0__, {QuestName}, {Itemname}, {NpcName}, {TerritoryName}. Copy EVERY placeholder into the Spanish text, same spelling and relative position.
GLOSSARY - follow it exactly:
- Keep MP, HP in English. Never PM, PH, mana, PV, PS.
- Endurance is "resistencia". Never "aguante".
- Latin American Spanish: "tu", never "vosotros". Never "coger". Use "tomar", "agarrar", "recoger" or "conseguir".
- Decimal comma: +1,42 not +1.42.

Do not add explanations. Do not include the English source in your output.
Translate EVERY sentence.
Never use raw line breaks inside the JSON strings you return.
Return ONLY valid JSON: an array of Spanish strings, same length and order as the input array.
""".strip()

DEFAULT_CACHE = "cache/quest_translation_cache.json"

CREDIT = item.CREDIT
FORBIDDEN_ES = item.FORBIDDEN_ES
KEEP_ENGLISH = item.KEEP_ENGLISH
ORPHAN_TAG_RE = item.ORPHAN_TAG_RE
TOOLTIP_RE = item.TOOLTIP_RE
describe_problems = item.describe_problems
engine_vars = item.engine_vars
looks_untranslated = item.looks_untranslated


def list_quest_files(root: Path, start: int, count: int) -> list[Path]:
    files = sorted(root.rglob("StrSheet_Quest-*.xml"))
    if not files:
        files = sorted(
            p
            for p in root.rglob("*.xml")
            if not p.name.endswith("_Translated.xml")
        )
    if start < 0:
        start = 0
    files = files[start:]
    if count > 0:
        files = files[:count]
    return files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Translate TERA StrSheet_Quest files in packs (one Gemini run, shared cache)."
    )
    parser.add_argument(
        "input_path",
        help="Folder with StrSheet_Quest-*.xml, or a single XML file",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default="output",
        help="Directory for *_Translated.xml (default: output)",
    )
    parser.add_argument(
        "--cache",
        default=DEFAULT_CACHE,
        help=f"Shared quest cache (default: {DEFAULT_CACHE})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="Unique strings per Gemini request (default: 20)",
    )
    parser.add_argument(
        "--start",
        type=int,
        default=0,
        help="Skip the first N files in the sorted folder (default: 0)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=50,
        help="How many files to translate in this pack. 0 = all remaining (default: 50)",
    )
    parser.add_argument(
        "--no-ascii-entities",
        action="store_true",
        help="Zapisz akcenty jako zwykle znaki UTF-8 zamiast encji",
    )
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
        files = list_quest_files(input_path, args.start, args.count)
        if not files:
            print(f"No quest XML files in {input_path}", file=sys.stderr)
            return 1
        last = files[-1].name
        print(
            f"Pack: {files[0].name} .. {last} ({len(files)} files, start={args.start})",
            flush=True,
        )
    else:
        print(f"Input not found: {input_path}", file=sys.stderr)
        return 1

    item.process_files(files, output_dir, cache_path, batch_size, ascii_safe)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
