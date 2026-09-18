"""
Translate TERA StrSheet_UI string attributes from English to Latin American Spanish.

UI XML differs from Item XML:
- visible text is string=, keyed by stringId= (e.g. $001012)
- there is no toolTip; labels, buttons and system messages live in string=
- output is compact bilingual: Inventory/Inventario (not the [EN]/[ES] tooltip block)
- key names (F1, Shift, W) stay English
- {placeholders} and {@select:...} must be copied unchanged

Usage:
    python translate_ui.py source/StrSheet_UI-00000.xml
    python translate_ui.py source/StrSheet_UI-00000.xml --batch-size 20 --limit 80
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

import translate_tooltips as item

item.TOOLTIP_RE = re.compile(r'(?<!Id)string="([^"]*)"')

BRACE_RE = re.compile(
    r"\{@(?:select|ordinal|plural):[^{}]*\{[^{}]*\}[^{}]*\}"
    r"|\{@[A-Za-z]+(?::[^{}]+)?\}"
    r"|\{[A-Za-z][A-Za-z0-9_]*\}"
)

item.MARKUP_RE = re.compile(
    item.TAG_RE.pattern + "|" + item.VAR_RE.pattern + "|" + BRACE_RE.pattern + r"|\x01"
)

item.KEEP_ENGLISH = item.KEEP_ENGLISH + ("Focus", "Rage")

KEYBIND_EXACT = {
    "ESC",
    "Esc",
    "Shift",
    "Alt",
    "Ctrl",
    "Control",
    "Enter",
    "Tab",
    "Space Bar",
    "Num Lock",
    "L-Click",
    "R-Click",
}

KEYBIND_RE = re.compile(
    r"^(?:F\d+|[A-Za-z]|[0-9]+|Num\s*Lock)$",
    re.I,
)


def should_leave_english(original: str) -> bool:
    """Klawisze, pojedyncze litery i same placeholdery nie ida do modelu."""
    text = html.unescape(original).replace("\n", " ").strip()
    if not text:
        return True
    if text in KEYBIND_EXACT:
        return True
    if KEYBIND_RE.fullmatch(text):
        return True
    if re.fullmatch(r"\{[A-Za-z][A-Za-z0-9_]*\}", text):
        return True
    return False


_orig_collect = item.collect_unique_uncached


def collect_unique_uncached(lines: list[str], cache: dict[str, str]) -> list[str]:
    unique = _orig_collect(lines, cache)
    return [text for text in unique if not should_leave_english(text)]


item.collect_unique_uncached = collect_unique_uncached


def to_tera_html_entities(text: str) -> str:
    """&amp;#243; w XML, zeby po Novadrop w stringu zostalo &#243;."""
    return "".join(c if ord(c) < 128 else f"&amp;#{ord(c)};" for c in text)


item.to_ascii_entities = to_tera_html_entities

UI_SEP = "/"


def split_ui_pair(original_attr: str, combined: str) -> tuple[str, str] | None:
    """Oddziela angielski od hiszpanskiego w formacie Inventory/Inventario."""
    english = item.balance_font_tags(item.sanitize(original_attr))
    prefix = english + UI_SEP
    if combined.startswith(prefix):
        return english, combined[len(prefix) :]
    return None


def ui_string(original_attr: str, spanish_escaped: str) -> str:
    """Etykieta UI: Inventory/Inventario, bez bloku [EN]/[ES]."""
    english = item.balance_font_tags(item.sanitize(original_attr))
    spanish = item.localize_headings(item.balance_font_tags(item.sanitize(spanish_escaped)))
    return f"{english}{UI_SEP}{spanish}"


item.bilingual_tooltip = ui_string

item.SYSTEM_PROMPT = """
You are an expert video game localizer. Translate TERA MMORPG user-interface strings from English to Spanish.

These are buttons, menu labels, system messages, character-creation lore and short help texts shown in the client UI. Translate the visible meaning into natural Latin American Spanish. Return ONLY the Spanish text - the local script prepends the English source as Inventory/Inventario.

Keep the tone consistent with a high fantasy action MMORPG. Prefer established Spanish MMO phrasing over literal calques.
Keep proper names (Kelsaik, Valkyon, Bahaar, Kaia, Elin, Castanic, Popori, Baraka, Amani, Velik, Arborea, etc.) unchanged unless a well-known Spanish TERA name already exists.
Class names used as proper labels stay in English: Warrior, Lancer, Berserker, Slayer, Sorcerer, Archer, Priest, Mystic, Reaper, Gunner, Brawler, Ninja, Valkyrie.
Skill, mount, emote, quest, dungeon, NPC and item names stay in English when they are names, not UI chrome. Translate chrome: Inventory, System, Learned Skills, Advance Skill, Cannot trade, No sale value.
Keyboard key names stay in English: F1-F12, Shift, Alt, Ctrl, Enter, Tab, ESC, Space Bar, and single letters used as hotkeys.
Anything inside square brackets that is a key or a proper menu path stays in English, e.g. [Alt]. Known descriptive headings may be localized.
Preserve numbers, percentages, and punctuation.
Placeholders like __TAG0__, __TAG1__, __TAG2__ are protected markup, game variables and brace tokens such as {name} or {@select:{hour}/s//s}. Copy EVERY one of them into the Spanish text, in the same relative positions, with the exact same spelling. Never translate, merge, renumber or delete them. The output must contain exactly the same placeholders as the input, no more and no fewer.
GLOSSARY - follow it exactly, it overrides your own preferences:
- Keep these words in English, spelled exactly as in the source, even inside Spanish sentences: MP, HP, Feedstock, Battle Solution, Spellbind, Alkahest, Noctenium, Everful Nostrum, Etching, Crystal, Emerald, Diamond, Talent, Focus, Rage.
- Never write PM, PH or "mana" for MP. Never write PV or PS for HP.
- Endurance is always "resistencia". Never "aguante".
- Power is "poder". Crit Power is "poder de golpe critico".
- "times" as a multiplier is "veces" - never leave the English word.
- Use the Spanish decimal comma: +1,42 not +1.42.
- The audience is Latin American, not Spain. Write neutral Latin American Spanish: address the player as "tu", never use "vosotros" or its verb forms, and avoid Spain-only vocabulary. Use "lentes" not "gafas", "saco" or "blazer" not "americana", "computadora" not "ordenador".
- Never use the verb "coger" in any form - it is vulgar in most of Latin America. Use "tomar", "agarrar", "recoger" or "conseguir" instead.

Do not add explanations, notes, quotes, or extra punctuation that was not implied by the source.
Do not include the English source text in your output.
Translate EVERY sentence.
Never use raw line breaks inside the JSON strings you return.
Return ONLY valid JSON: an array of Spanish strings, same length and order as the input array.
""".strip()

DEFAULT_CACHE = "cache/ui_translation_cache.json"

CREDIT = item.CREDIT
FORBIDDEN_ES = item.FORBIDDEN_ES
KEEP_ENGLISH = item.KEEP_ENGLISH
ORPHAN_TAG_RE = item.ORPHAN_TAG_RE
TOOLTIP_RE = item.TOOLTIP_RE
describe_problems = item.describe_problems
engine_vars = item.engine_vars
looks_untranslated = item.looks_untranslated


def brace_tokens(text: str) -> list[str]:
    """Wypisuje tokeny {placeholder} razem z zagniezdzeniem {@select:{hour}/s//s}."""
    decoded = html.unescape(text)
    found: list[str] = []
    index = 0
    while index < len(decoded):
        if decoded[index] != "{":
            index += 1
            continue
        depth = 0
        end = index
        closed = False
        while end < len(decoded):
            if decoded[end] == "{":
                depth += 1
            elif decoded[end] == "}":
                depth -= 1
                if depth == 0:
                    found.append(decoded[index : end + 1])
                    index = end
                    closed = True
                    break
            end += 1
        if not closed:
            break
        index += 1
    return sorted(found)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Translate TERA StrSheet_UI strings to Latin American Spanish via Gemini."
    )
    parser.add_argument("input_xml", help="Source StrSheet_UI XML file")
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output XML path (default: output/<name>_Translated.xml)",
    )
    parser.add_argument(
        "--cache",
        default=DEFAULT_CACHE,
        help=f"Shared UI translation cache (default: {DEFAULT_CACHE})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=item.BATCH_SIZE,
        help=f"Unique strings per Gemini request (default: {item.BATCH_SIZE})",
    )
    parser.add_argument(
        "--no-ascii-entities",
        action="store_true",
        help="Zapisz akcenty jako zwykle znaki UTF-8 zamiast encji",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Only process the first N lines - useful for a cheap test run",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input_xml).expanduser()
    if not input_path.is_file():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        return 1

    if args.output:
        output_path = Path(args.output).expanduser()
    else:
        output_path = Path("output") / f"{input_path.stem}_Translated{input_path.suffix}"

    cache_path = Path(args.cache).expanduser()
    batch_size = args.batch_size if args.batch_size > 0 else item.BATCH_SIZE
    limit = args.limit if args.limit > 0 else None

    item.process_file(
        input_path,
        output_path,
        cache_path,
        batch_size,
        limit,
        not args.no_ascii_entities,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
