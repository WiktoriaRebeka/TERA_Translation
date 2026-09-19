"""
Kontrola jakosci StrSheet_Npc (compact English/Spanish).
"""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

from translate_npc import (
    FORBIDDEN_ES,
    describe_problems,
    looks_untranslated,
    should_leave_english,
    split_ui_pair,
)


def load_entries(path: Path) -> dict[str, str]:
    root = ET.parse(path).getroot()
    entries: dict[str, str] = {}
    for element in root:
        identifier = element.get("id") or ""
        if identifier:
            entries[identifier] = element.get("string") or ""
    return entries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("translated")
    parser.add_argument("--source", default=None)
    args = parser.parse_args()
    translated_path = Path(args.translated)
    if translated_path.is_dir():
        files = sorted(translated_path.glob("StrSheet_Npc-*.xml"))
    else:
        files = [translated_path]
    problems = 0
    for path in files:
        source = None
        if args.source:
            src = Path(args.source)
            source = src / path.name.replace("_Translated", "") if src.is_dir() else src
        entries = load_entries(path)
        source_entries = load_entries(source) if source and source.is_file() else {}
        for identifier, value in entries.items():
            original = source_entries.get(identifier, "")
            if not value or should_leave_english(original or value):
                continue
            pair = split_ui_pair(original, value) if original else None
            if pair is None:
                print(f"{path.name} id={identifier}: brak pary EN/ES")
                problems += 1
                continue
            english, spanish = pair
            issues = describe_problems(original, spanish)
            if looks_untranslated(html.unescape(spanish), html.unescape(english)):
                issues.append("looks untranslated")
            for forbidden in FORBIDDEN_ES:
                if forbidden:
                    pass
            if issues:
                print(f"{path.name} id={identifier}: {issues[:3]}")
                problems += 1
    print(f"Npc check problems: {problems}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
