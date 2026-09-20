"""
Translate TERA VillagerDialog parchment pages (merchant/guard greetings).

Same <Page>inner</Page> bilingual [EN]/[ES] as QuestDialog, no credit.
TEXTBUTTON / EVENTPAGEBUTTON / page buttons stay English.

Usage:
    python translate_villagerdialog.py source/VillagerDialog
    python translate_villagerdialog.py source/VillagerDialog --start 0 --count 0
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import translate_questdialog as qd
import translate_tooltips as item

qd.BUTTON_RE = re.compile(
    r"(&lt;(?:NEXTPAGEBUTTON|PREVPAGEBUTTON|CLOSEPAGEBUTTON|"
    r"TEXTBUTTON|EVENTPAGEBUTTON)&gt;)(.*?)(&lt;/"
    r"(?:NEXTPAGEBUTTON|PREVPAGEBUTTON|CLOSEPAGEBUTTON|"
    r"TEXTBUTTON|EVENTPAGEBUTTON)&gt;)",
    re.DOTALL | re.IGNORECASE,
)

item.to_ascii_entities = item.to_tera_html_entities

item.SYSTEM_PROMPT = """
You are an expert video game localizer. Translate TERA MMORPG NPC greeting dialogue from English to Spanish.

These are parchment speeches when talking to merchants, guards, trainers and other villagers (not quest-specific). Translate meaning naturally into Latin American Spanish. Keep the tone of high fantasy TERA.
Keep proper names unchanged: NPCs, places, dungeons, items, skills, classes, races, AND monster names. Place names stay English: Isolated Town, Island of Dawn, Velika, Oblivion Woods, Bestial Vale, Bastion of Lok.
Class and race names stay English.
Placeholders like __TAG0__ and markup must be copied unchanged, same spelling and relative position.
Copy {@linkcreature:...}, {@linkitem:...} and other {@...} tags verbatim, including English place and NPC names inside them (Allemantheia Headquarters, Flight Manager, speak to the gatekeeper to enter).
Text inside NEXTPAGEBUTTON, PREVPAGEBUTTON, CLOSEPAGEBUTTON, TEXTBUTTON and EVENTPAGEBUTTON stays English (F-choices, Confirm/Cancel, dungeon names).
GLOSSARY:
- Keep MP, HP in English. Never PM, PH, mana, PV, PS.
- Endurance is "resistencia". Never "aguante".
- Latin American Spanish: "tu", never "vosotros". Never "coger". Use "tomar", "agarrar", "recoger" or "conseguir".
- Decimal comma: +1,42 not +1.42.

Do not add explanations. Do not include the English source in your output.
Translate EVERY sentence.
Never use raw line breaks inside the JSON strings you return.
Return ONLY valid JSON: an array of Spanish strings, same length and order as the input array.
""".strip()

DEFAULT_CACHE = "cache/villagerdialog_translation_cache.json"
PAGE_RE = qd.PAGE_RE
CREDIT = item.CREDIT
FORBIDDEN_ES = item.FORBIDDEN_ES
KEEP_ENGLISH = item.KEEP_ENGLISH
describe_problems = item.describe_problems
engine_vars = item.engine_vars
looks_untranslated = item.looks_untranslated
salvage_leaked_cache = qd.salvage_leaked_cache
collect_unique = qd.collect_unique
rewrite_dialog = qd.rewrite_dialog


def list_dialog_files(root: Path, start: int, count: int) -> list[Path]:
    files = sorted(root.glob("VillagerDialog-*.xml"))
    if start < 0:
        start = 0
    files = files[start:]
    if count > 0:
        files = files[:count]
    return files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Translate TERA VillagerDialog parchment pages to bilingual EN/ES."
    )
    parser.add_argument("input_path")
    parser.add_argument("-o", "--output-dir", default="output/VillagerDialog")
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
        files = list_dialog_files(input_path, args.start, args.count)
        if not files:
            print(f"No VillagerDialog XML in {input_path}", file=sys.stderr)
            return 1
        print(
            f"Pack: {files[0].name} .. {files[-1].name} ({len(files)} files, start={args.start})",
            flush=True,
        )
    else:
        print(f"Input not found: {input_path}", file=sys.stderr)
        return 1

    cache = item.load_cache(cache_path)
    salvaged = salvage_leaked_cache(cache)
    if salvaged:
        print(f"Salvaged {salvaged} pages from leaked XML cache keys.", flush=True)
    unique = collect_unique(files, cache)
    print(f"Cache: {cache_path} ({len(cache)} known); missing {len(unique)}", flush=True)
    if unique:
        api_key = (item.GEMINI_API_KEY or "").strip() or os.environ.get(
            "GEMINI_API_KEY", ""
        ).strip()
        if api_key:
            client = item.build_client()
            item.fill_cache_in_batches(unique, client, cache, cache_path, batch_size)
        else:
            print("Leaving missing pages in English (no Gemini this pass).", flush=True)
    else:
        print("All non-empty pages are already in the cache.", flush=True)

    output_dir.mkdir(parents=True, exist_ok=True)
    applied_total = 0
    for path in files:
        raw = path.read_bytes()
        newline = b"\r\n" if b"\r\n" in raw[:200] else b"\n"
        new_text, applied = rewrite_dialog(raw.decode("utf-8"), cache, ascii_safe)
        out = new_text.encode("utf-8")
        if newline == b"\r\n":
            out = out.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        dest = output_dir / f"{path.stem}_Translated{path.suffix}"
        dest.write_bytes(out)
        applied_total += applied
    item.save_cache(cache_path, cache)
    print(f"Wrote {len(files)} files, bilingual pages: {applied_total}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
