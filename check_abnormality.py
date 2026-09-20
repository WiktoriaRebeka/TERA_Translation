"""
Kontrola jakosci StrSheet_Abnormality (tooltip= dwujezyczne) i Kind (compact).
name= buffow zostaje po angielsku.
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

from translate_abnormality import KIND_COMPACT, describe_problems, looks_untranslated

TOOLTIP_RE = re.compile(r'\btooltip="([^"]*)"')
KIND_NAME_RE = re.compile(r'\bname="([^"]*)"')


def halves(text: str) -> tuple[str, str] | None:
    decoded = html.unescape(text)
    if "[ES]" not in decoded:
        return None
    english, spanish = decoded.split("[ES]", 1)
    english = english.replace("[EN]", "", 1).replace("<br>", "").strip()
    spanish = re.sub(r"<br>\s*$", "", spanish).strip()
    return english, spanish


def check_tooltips(files: list[Path]) -> tuple[int, int, int]:
    problems = 0
    bilingual = 0
    left = 0
    for path in files:
        text = path.read_text(encoding="utf-8")
        for match in TOOLTIP_RE.finditer(text):
            value = match.group(1)
            if not value:
                continue
            pair = halves(value)
            if pair is None:
                left += 1
                continue
            bilingual += 1
            english, spanish = pair
            issues = describe_problems(english, spanish)
            if looks_untranslated(english, spanish):
                issues.append("looks untranslated")
            if issues:
                print(f"{path.name}: {issues[:3]}")
                problems += 1
    print(f"Abnormality bilingual={bilingual} left={left} problems={problems}")
    return bilingual, left, problems


def check_kind(files: list[Path]) -> int:
    compact = 0
    left = 0
    for path in files:
        text = path.read_text(encoding="utf-8")
        for match in KIND_NAME_RE.finditer(text):
            value = html.unescape(match.group(1))
            if not value:
                continue
            if "/" in value or value in KIND_COMPACT:
                if "/" in value:
                    compact += 1
                else:
                    left += 1
            else:
                left += 1
    print(f"AbnormalityKind compact={compact} left={left}")
    return left


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("translated", nargs="?", default="output/StrSheet_Abnormality")
    parser.add_argument("--kind", default="output/StrSheet_AbnormalityKind")
    args = parser.parse_args()
    translated_path = Path(args.translated)
    kind_path = Path(args.kind)
    problems = 0
    if not translated_path.exists():
        print(f"Abnormality output not found yet: {translated_path}")
    else:
        files = (
            sorted(translated_path.glob("StrSheet_Abnormality-*.xml"))
            if translated_path.is_dir()
            else [translated_path]
        )
        _bilingual, _left, problems = check_tooltips(files)
    if kind_path.exists():
        kind_files = (
            sorted(kind_path.glob("StrSheet_AbnormalityKind-*.xml"))
            if kind_path.is_dir()
            else [kind_path]
        )
        check_kind(kind_files)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
