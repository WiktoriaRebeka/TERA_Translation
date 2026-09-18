"""
Kontrola jakosci przetlumaczonego StrSheet_Quest (pojedynczy plik albo folder).

Uzycie:
    python check_quest.py output/StrSheet_Quest-00000_Translated.xml
    python check_quest.py output/StrSheet_Quest --source source/StrSheet_Quest
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

from translate_quest import (
    CREDIT,
    FORBIDDEN_ES,
    KEEP_ENGLISH,
    ORPHAN_TAG_RE,
    describe_problems,
    engine_vars,
    looks_untranslated,
    should_leave_english,
)

SEPARATOR = "<br>[ES]"
CREDIT_MARK = f"<br><font color='#555555'>{CREDIT}"


def load_entries(path: Path) -> dict[str, str]:
    root = ET.parse(path).getroot()
    entries: dict[str, str] = {}
    for element in root:
        identifier = element.get("id") or ""
        if identifier:
            entries[identifier] = element.get("string") or ""
    return entries


def split_halves(text: str) -> tuple[str, str] | None:
    if SEPARATOR not in text:
        return None
    english, rest = text.split(SEPARATOR, 1)
    english = english.replace("[EN] ", "", 1)
    spanish = rest.split(CREDIT_MARK)[0]
    return english, spanish


def normalize(text: str) -> str:
    return " ".join(html.unescape(text).split())


def check_one(translated_path: Path, source_path: Path | None, max_examples: int) -> int:
    problems: dict[str, list[str]] = {}

    def add(label: str, detail: str) -> None:
        problems.setdefault(label, []).append(detail)

    print(f"Sprawdzam {translated_path.name}")
    try:
        entries = load_entries(translated_path)
    except ET.ParseError as exc:
        print(f"  KRYTYCZNE: {exc}")
        return 1

    source_entries: dict[str, str] = {}
    if source_path and source_path.is_file():
        source_entries = load_entries(source_path)

    translated = 0
    left = 0
    skipped = 0
    for identifier, text in entries.items():
        original = source_entries.get(identifier, "")
        if original and should_leave_english(original):
            skipped += 1
            continue
        if not text:
            continue
        if ORPHAN_TAG_RE.search(text):
            add("resztki placeholderow", identifier)
        halves = split_halves(text)
        if halves is None:
            left += 1
            continue
        translated += 1
        english, spanish = halves
        if original and engine_vars(original) != engine_vars(spanish):
            info = describe_problems(original, spanish)
            add(
                "rozjechane zmienne",
                f"{identifier}: {info[0] if info else 'mismatch'}",
            )
        if original and looks_untranslated(original, spanish):
            add("zdanie po angielsku", identifier)
        plain_es = html.unescape(spanish)
        for forbidden in FORBIDDEN_ES:
            found = re.search(forbidden, plain_es, re.I)
            if found:
                add(f"zakazane {found.group(0)}", identifier)
        for term in KEEP_ENGLISH:
            pattern = r"\b" + re.escape(term)
            if original and re.search(pattern, html.unescape(original), re.I) and not re.search(
                pattern, plain_es, re.I
            ):
                add(f"zgubiony {term}", identifier)

    print(f"  dwujezyczne {translated}, bez ES {left}, animacje {skipped}")
    if problems:
        total = sum(len(v) for v in problems.values())
        print(f"  problemy: {total}")
        for label in sorted(problems, key=lambda k: -len(problems[k])):
            found = problems[label]
            print(f"    {label}: {len(found)}")
            for detail in found[:max_examples]:
                print(f"      {detail}")
        return 1
    print("  OK")
    return 0


def guess_source(translated_path: Path, source_root: Path | None) -> Path | None:
    stem = translated_path.stem.replace("_Translated", "")
    if source_root and source_root.is_dir():
        candidate = source_root / f"{stem}{translated_path.suffix}"
        if candidate.is_file():
            return candidate
    if source_root and source_root.is_file():
        return source_root
    default = Path("source") / "StrSheet_Quest" / f"{stem}{translated_path.suffix}"
    return default if default.is_file() else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Sprawdza przetlumaczone StrSheet_Quest.")
    parser.add_argument("translated", help="Plik *_Translated.xml albo folder output/")
    parser.add_argument(
        "--source",
        default=None,
        help="Zrodlo: plik albo folder source/StrSheet_Quest",
    )
    parser.add_argument("--max-examples", type=int, default=3)
    args = parser.parse_args()

    translated = Path(args.translated)
    source_arg = Path(args.source) if args.source else None
    if translated.is_dir():
        files = sorted(translated.glob("StrSheet_Quest-*_Translated.xml"))
    else:
        files = [translated]

    if not files:
        print("Brak plikow do sprawdzenia.", file=sys.stderr)
        return 2

    failed = 0
    for path in files:
        src = guess_source(path, source_arg)
        failed += check_one(path, src, args.max_examples)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
