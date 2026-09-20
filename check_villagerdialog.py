"""
Kontrola jakosci VillagerDialog (strony pergaminu [EN]/[ES]).

Przyciski F / Confirm / nazwy dungeona w TEXTBUTTON i EVENTPAGEBUTTON
zostaja po angielsku.
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

from translate_questdialog import PAGE_RE, describe_problems, looks_untranslated

KEEP_ENGLISH_INNER_RE = re.compile(
    r"<(?:NEXTPAGEBUTTON|PREVPAGEBUTTON|CLOSEPAGEBUTTON|"
    r"TEXTBUTTON|EVENTPAGEBUTTON)>.*?</(?:NEXTPAGEBUTTON|"
    r"PREVPAGEBUTTON|CLOSEPAGEBUTTON|TEXTBUTTON|EVENTPAGEBUTTON)>",
    re.DOTALL | re.IGNORECASE,
)


def halves(text: str) -> tuple[str, str] | None:
    decoded = html.unescape(text)
    if "[ES]" not in decoded:
        return None
    english, spanish = decoded.split("[ES]", 1)
    english = english.replace("[EN]", "", 1).replace("<br>", "").strip()
    spanish = spanish.strip()
    return english, spanish


def strip_kept_english(text: str) -> str:
    return KEEP_ENGLISH_INNER_RE.sub("", text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("translated")
    parser.add_argument("--source", default=None)
    args = parser.parse_args()
    translated_path = Path(args.translated)
    if not translated_path.exists():
        print(f"VillagerDialog output not found yet: {translated_path}")
        return 0
    files = (
        sorted(translated_path.glob("VillagerDialog-*.xml"))
        if translated_path.is_dir()
        else [translated_path]
    )
    problems = 0
    bilingual = 0
    left = 0
    for path in files:
        text = path.read_text(encoding="utf-8")
        for match in PAGE_RE.finditer(text):
            inner = match.group(2)
            if not inner.strip():
                continue
            pair = halves(inner)
            if pair is None:
                left += 1
                continue
            bilingual += 1
            english, spanish = pair
            english = strip_kept_english(english)
            spanish = strip_kept_english(spanish)
            issues = describe_problems(english, spanish)
            if looks_untranslated(english, spanish):
                issues.append("looks untranslated")
            if issues:
                print(f"{path.name}: {issues[:3]}")
                problems += 1
    print(f"VillagerDialog bilingual={bilingual} left={left} problems={problems}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
