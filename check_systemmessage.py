"""Kontrola jakosci StrSheet_SystemMessage: sam ES, tokeny {}, porownanie z EN source."""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

from translate_systemmessage import ATTR_RE, BRACE_RE, describe_problems, looks_untranslated

READABLE_RE = re.compile(r'\breadableId="([^"]+)"')


def load_strings(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    files = (
        sorted(path.glob("StrSheet_SystemMessage-*.xml"))
        if path.is_dir()
        else [path]
    )
    for file in files:
        for line in file.read_text(encoding="utf-8").splitlines():
            ident = READABLE_RE.search(line)
            match = ATTR_RE.search(line)
            if ident and match:
                out[ident.group(1)] = match.group(1)
    return out


def brace_tokens(text: str) -> list[str]:
    return BRACE_RE.findall(html.unescape(text))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("translated", nargs="?", default="output/StrSheet_SystemMessage")
    parser.add_argument("--source", default="source/StrSheet_SystemMessage")
    args = parser.parse_args()
    translated_path = Path(args.translated)
    source_path = Path(args.source)
    if not translated_path.exists():
        print(f"SystemMessage output not found yet: {translated_path}")
        return 0
    spanish = load_strings(translated_path)
    english = load_strings(source_path) if source_path.exists() else {}
    problems = 0
    applied = 0
    leftover = 0
    bilingual = 0
    for key, value in spanish.items():
        if not value:
            continue
        decoded = html.unescape(value)
        if "[EN]" in decoded or "[ES]" in decoded:
            print(f"{key}: leftover bilingual labels")
            bilingual += 1
            problems += 1
            continue
        src = english.get(key, "")
        if not src:
            applied += 1
            continue
        issues = describe_problems(src, value)
        if brace_tokens(src) != brace_tokens(value):
            issues.append("brace token mismatch")
        if looks_untranslated(src, value):
            leftover += 1
            issues.append("looks untranslated")
        else:
            applied += 1
        if issues:
            print(f"{key}: {issues[:3]}")
            problems += 1
    print(
        f"SystemMessage applied={applied} leftover_en={leftover} "
        f"bilingual={bilingual} problems={problems}"
    )
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
