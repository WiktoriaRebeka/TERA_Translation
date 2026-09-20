"""Kontrola jakosci StrSheet_SystemMessage (string= dwujezyczne, tokeny {})."""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

from translate_systemmessage import ATTR_RE, BRACE_RE, describe_problems, looks_untranslated


def halves(text: str) -> tuple[str, str] | None:
    decoded = html.unescape(text)
    if "[ES]" not in decoded:
        return None
    english, spanish = decoded.split("[ES]", 1)
    english = english.replace("[EN]", "", 1).replace("<br>", "").strip()
    spanish = re.sub(r"<br>\s*$", "", spanish).strip()
    return english, spanish


def brace_tokens(text: str) -> list[str]:
    return BRACE_RE.findall(html.unescape(text))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("translated", nargs="?", default="output/StrSheet_SystemMessage")
    args = parser.parse_args()
    translated_path = Path(args.translated)
    if not translated_path.exists():
        print(f"SystemMessage output not found yet: {translated_path}")
        return 0
    files = (
        sorted(translated_path.glob("StrSheet_SystemMessage-*.xml"))
        if translated_path.is_dir()
        else [translated_path]
    )
    problems = 0
    bilingual = 0
    left = 0
    for path in files:
        text = path.read_text(encoding="utf-8")
        for match in ATTR_RE.finditer(text):
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
            if brace_tokens(english) != brace_tokens(spanish):
                issues.append("brace token mismatch")
            if issues:
                print(f"{path.name}: {issues[:3]}")
                problems += 1
    print(f"SystemMessage bilingual={bilingual} left={left} problems={problems}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
