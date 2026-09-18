"""
Kontrola jakosci przetlumaczonego StrSheet_UI.

Porownuje plik wynikowy z oryginalem po stringId: placeholdery {name},
znaczniki HTML, klawisze zostawione po angielsku, zakazane slowa ES.

UI nie uzywa bloku [EN]/[ES] - etykieta ma byc po hiszpansku.

Uzycie:
    python check_ui.py output/StrSheet_UI-00000_Translated.xml
    python check_ui.py output/plik.xml --source source/plik.xml
    python check_ui.py output/plik.xml --report raport.txt
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

from translate_ui import (
    FORBIDDEN_ES,
    KEEP_ENGLISH,
    ORPHAN_TAG_RE,
    brace_tokens,
    describe_problems,
    engine_vars,
    looks_untranslated,
    should_leave_english,
    split_ui_pair,
)


def load_entries(path: Path) -> dict[str, str]:
    root = ET.parse(path).getroot()
    entries: dict[str, str] = {}
    for element in root:
        identifier = element.get("stringId") or ""
        if not identifier:
            continue
        entries[identifier] = element.get("string") or ""
    return entries


def normalize(text: str) -> str:
    return " ".join(html.unescape(text).split())


def font_balance(text: str) -> int:
    plain = html.unescape(text)
    return len(re.findall(r"<font\b", plain, re.I)) - len(
        re.findall(r"</font\b", plain, re.I)
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sprawdza jakosc przetlumaczonego StrSheet_UI."
    )
    parser.add_argument("translated", help="Plik wynikowy do sprawdzenia")
    parser.add_argument(
        "--source",
        default=None,
        help="Plik zrodlowy (domyslnie source/<nazwa bez _Translated>.xml)",
    )
    parser.add_argument("--report", default=None, help="Zapisz liste problemow do pliku")
    parser.add_argument(
        "--max-examples", type=int, default=5, help="Ile przykladow pokazac na problem"
    )
    args = parser.parse_args()

    translated_path = Path(args.translated)
    if not translated_path.is_file():
        print(f"Nie znaleziono pliku: {translated_path}", file=sys.stderr)
        return 2

    if args.source:
        source_path = Path(args.source)
    else:
        stem = translated_path.stem.replace("_Translated", "")
        source_path = Path("source") / f"{stem}{translated_path.suffix}"

    with translated_path.open("r", encoding="utf-8", newline="") as handle:
        raw = handle.read()

    problems: dict[str, list[str]] = {}
    info: dict[str, int] = {}

    def add(label: str, detail: str) -> None:
        problems.setdefault(label, []).append(detail)

    print(f"Sprawdzam {translated_path.name}")
    print("=" * 60)

    try:
        entries = load_entries(translated_path)
    except ET.ParseError as exc:
        print(f"KRYTYCZNE: plik nie jest poprawnym XML - {exc}")
        return 1
    print(f"XML parsuje sie poprawnie, wpisow: {len(entries)}")

    source_entries: dict[str, str] = {}
    if source_path.is_file():
        with source_path.open("r", encoding="utf-8", newline="") as handle:
            source_raw = handle.read()
        source_entries = load_entries(source_path)
        lines_src = len(source_raw.splitlines())
        lines_out = len(raw.splitlines())
        status = "zgodne" if lines_src == lines_out else "ROZNICA"
        print(f"Linie: zrodlo {lines_src}, wynik {lines_out} -> {status}")
        if lines_src != lines_out:
            add("liczba linii", f"{lines_src} -> {lines_out}")

        missing = set(source_entries) - set(entries)
        extra = set(entries) - set(source_entries)
        print(f"stringId: brakujace {len(missing)}, nadmiarowe {len(extra)}")
        for identifier in sorted(missing)[: args.max_examples]:
            add("brakujace stringId", identifier)
        for identifier in sorted(extra)[: args.max_examples]:
            add("nadmiarowe stringId", identifier)
    else:
        print(f"(pomijam porownanie ze zrodlem - nie znaleziono {source_path})")

    non_ascii = sorted({c for c in raw if ord(c) > 127})
    if non_ascii:
        add("znaki spoza ASCII", "".join(non_ascii[:20]))
    print(
        f"Czysty ASCII: {'tak' if not non_ascii else 'NIE (' + str(len(non_ascii)) + ' roznych znakow)'}"
    )
    html_entities = raw.count("&amp;#")
    if html_entities:
        info["encje &amp;# (akcenty LATAM dla klienta TERA)"] = html_entities

    counts = {"puste": 0, "klawisze": 0, "przetlumaczone": 0, "zostawione EN": 0}

    for identifier, text in entries.items():
        if not text:
            counts["puste"] += 1
            continue
        if ORPHAN_TAG_RE.search(text):
            add("resztki placeholderow", identifier)
        if font_balance(text) != 0:
            add("niezbalansowany <font>", f"{identifier} ({font_balance(text):+d})")
        original = source_entries.get(identifier, "")
        if original and should_leave_english(original):
            counts["klawisze"] += 1
            if normalize(original) != normalize(text):
                add("zmieniony klawisz/hotkey", f"{identifier}: {text!r}")
            continue

        pair = split_ui_pair(original, text) if original else None
        if pair is None:
            if original and normalize(original) == normalize(text):
                counts["zostawione EN"] += 1
            else:
                counts["zostawione EN"] += 1
                add("brak formatu EN/ES (Inventory/Inventario)", identifier)
            continue

        counts["przetlumaczone"] += 1
        _english, spanish = pair
        if brace_tokens(original) != brace_tokens(spanish):
            add("rozjechane {placeholdery}", identifier)
        if engine_vars(original) != engine_vars(spanish):
            problems_list = describe_problems(original, spanish)
            add(
                "rozjechane zmienne silnika",
                f"{identifier}: {problems_list[0] if problems_list else 'mismatch'}",
            )
        if looks_untranslated(original, spanish):
            add("zdanie zostawione po angielsku", identifier)
        plain_es = html.unescape(spanish)
        for term in KEEP_ENGLISH:
            pattern = r"\b" + re.escape(term)
            if re.search(pattern, html.unescape(original), re.I) and not re.search(
                pattern, plain_es, re.I
            ):
                add(f"zgubiony termin {term}", identifier)
        for forbidden in FORBIDDEN_ES:
            found = re.search(forbidden, plain_es, re.I)
            if found:
                add(f"zakazane slowo {found.group(0)}", identifier)

    print(
        f"Stringi: {counts['przetlumaczone']} w formacie EN/ES, "
        f"{counts['zostawione EN']} nadal EN, "
        f"{counts['klawisze']} klawiszy, "
        f"{counts['puste']} pustych"
    )

    if info:
        print()
        for label, count in info.items():
            print(f"Informacja: {label}: {count}")

    print()
    print("=" * 60)
    if not problems:
        print("BEZ ZASTRZEZEN - plik przeszedl wszystkie kontrole.")
        return 0

    print(f"ZNALEZIONE PROBLEMY ({sum(len(v) for v in problems.values())} wystapien):")
    print()
    for label in sorted(problems, key=lambda k: -len(problems[k])):
        found = problems[label]
        print(f"  {label}: {len(found)}")
        for detail in found[: args.max_examples]:
            print(f"      {detail}")
        if len(found) > args.max_examples:
            print(f"      ... i {len(found) - args.max_examples} wiecej")

    if args.report:
        report = Path(args.report)
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open("w", encoding="utf-8") as handle:
            for label in sorted(problems):
                handle.write(f"## {label} ({len(problems[label])})\n")
                for detail in problems[label]:
                    handle.write(f"{detail}\n")
                handle.write("\n")
        print()
        print(f"Pelna lista zapisana w {report}")

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
