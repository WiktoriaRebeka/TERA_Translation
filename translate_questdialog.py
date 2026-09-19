"""
Translate TERA QuestDialog parchment pages (NPC quest speech).

XML uses <Page>inner text</Page>, not string=. Bilingual [EN]/[ES], no credit.
Monster, place, NPC and item names stay English.

Usage:
    python translate_questdialog.py source/QuestDialog
    python translate_questdialog.py source/QuestDialog --start 0 --count 50
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import translate_tooltips as item

PAGE_RE = re.compile(r"(<Page\b[^>]*>)(.*?)(</Page>)", re.DOTALL)

item.OUTPUT_TEMPLATE = (
    "[EN] {english}"
    "&lt;br&gt;"
    "[ES] {spanish}"
)


def to_tera_html_entities(text: str) -> str:
    return "".join(c if ord(c) < 128 else f"&amp;#{ord(c)};" for c in text)


item.to_ascii_entities = to_tera_html_entities


item.SYSTEM_PROMPT = """
You are an expert video game localizer. Translate TERA MMORPG NPC quest dialogue from English to Spanish.

These are parchment speeches when accepting or turning in a quest. Translate meaning naturally into Latin American Spanish. Keep the tone of high fantasy TERA.
Keep proper names unchanged: NPCs, places, dungeons, items, skills, classes, races, AND monster names (Argon Predator, Slinking Sabertooth). Write "Derrota a los Argon Predator", never a Spanish creature name.
Place names stay English: Isolated Town, Island of Dawn, Velika, Fey Forest, Maon's Cabin, Valkyon Federation Headquarters.
Class and race names stay English.
Placeholders like __TAG0__ and markup must be copied unchanged, same spelling and relative position.
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

DEFAULT_CACHE = "cache/questdialog_translation_cache.json"
CREDIT = item.CREDIT
FORBIDDEN_ES = item.FORBIDDEN_ES
KEEP_ENGLISH = item.KEEP_ENGLISH
ORPHAN_TAG_RE = item.ORPHAN_TAG_RE
describe_problems = item.describe_problems
engine_vars = item.engine_vars
looks_untranslated = item.looks_untranslated


def list_dialog_files(root: Path, start: int, count: int) -> list[Path]:
    files = sorted(root.glob("QuestDialog-*.xml"))
    if start < 0:
        start = 0
    files = files[start:]
    if count > 0:
        files = files[:count]
    return files


def pages_in_text(xml_text: str) -> list[str]:
    found: list[str] = []
    for match in PAGE_RE.finditer(xml_text):
        inner = match.group(2)
        if inner.strip():
            found.append(inner)
    return found


def collect_unique(files: list[Path], cache: dict[str, str]) -> list[str]:
    unique: list[str] = []
    seen = set(cache.keys())
    for path in files:
        xml_text = path.read_text(encoding="utf-8")
        for original in pages_in_text(xml_text):
            if original in seen:
                continue
            if item.is_already_bilingual(original):
                continue
            seen.add(original)
            unique.append(original)
    return unique


def rewrite_dialog(xml_text: str, cache: dict[str, str], ascii_safe: bool) -> tuple[str, int]:
    applied = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal applied
        inner = match.group(2)
        if not inner.strip():
            return match.group(0)
        if item.is_already_bilingual(inner):
            return match.group(0)
        spanish_escaped = cache.get(inner)
        if spanish_escaped is None:
            return match.group(0)
        new_value = item.bilingual_tooltip(inner, spanish_escaped)
        applied += 1
        return f"{match.group(1)}{new_value}{match.group(3)}"

    new_text = PAGE_RE.sub(repl, xml_text)
    if ascii_safe:
        new_text = item.ascii_safe_line(new_text)
    return new_text, applied


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Translate TERA QuestDialog parchment pages to bilingual EN/ES."
    )
    parser.add_argument("input_path")
    parser.add_argument("-o", "--output-dir", default="output/QuestDialog")
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
            print(f"No QuestDialog XML in {input_path}", file=sys.stderr)
            return 1
        print(
            f"Pack: {files[0].name} .. {files[-1].name} ({len(files)} files, start={args.start})",
            flush=True,
        )
    else:
        print(f"Input not found: {input_path}", file=sys.stderr)
        return 1

    cache = item.load_cache(cache_path)
    unique = collect_unique(files, cache)
    print(f"Cache: {cache_path} ({len(cache)} known); missing {len(unique)}", flush=True)
    if unique:
        client = item.build_client()
        item.fill_cache_in_batches(unique, client, cache, cache_path, batch_size)
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
