"""
Kontrola jakosci StrSheet_Passivity (name= i tooltip= dwujezyczne).
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

from translate_passivity import describe_problems, looks_untranslated

ATTR_RE = re.compile(r'\b(name|tooltip)="([^"]*)"')
SEPARATOR = "[ES]"


def halves(text: str) -> tuple[str, str] | None:
    decoded = html.unescape(text)
    if "[ES]" not in decoded:
        return None
    english, spanish = decoded.split("[ES]", 1)
    english = english.replace("[EN]", "", 1).replace("<br>", "").strip()
    spanish = re.sub(r"<br>\s*$", "", spanish).strip()
    return english, spanish


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("translated")
    parser.add_argument("--source", default=None)
    args = parser.parse_args()
    translated_path = Path(args.translated)
    files = (
        sorted(translated_path.glob("StrSheet_Passivity-*.xml"))
        if translated_path.is_dir()
        else [translated_path]
    )
    problems = 0
    bilingual = 0
    left = 0
    for path in files:
        text = path.read_text(encoding="utf-8")
        for match in ATTR_RE.finditer(text):
            value = match.group(2)
            if not value:
                continue
            pair = halves(value)
            if pair is None:
                left += 1
                continue
            bilingual += 1
            english, spanish = pair
            issues = describe_problems(english, spanish)
            if looks_untranslated(spanish, english):
                issues.append("looks untranslated")
            if issues:
                print(f"{path.name} {match.group(1)}: {issues[:3]}")
                problems += 1
    print(f"Passivity bilingual={bilingual} left={left} problems={problems}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
