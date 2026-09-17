"""
Kontrola jakosci przetlumaczonego StrSheet_UserSkill.

Porownuje plik wynikowy z oryginalem i sprawdza wszystko, co moze sie zepsuc:
strukture, kodowanie, zmienne silnika, znaczniki koloru, kompletnosc
tlumaczenia i spojnosc terminologii.

W UserSkill to samo id moze wystapic wiele razy (raz na klase), wiec
wpisy sa identyfikowane jako id|class|kolejnosc, nie samym id.

Korzysta z glossary i walidatorow z translate_userskill.py
(a tamte z translate_tooltips.py), wiec slowniczek zostaje wspolny.

Uzycie:
    python check_userskill.py output/StrSheet_UserSkill-00001_Translated.xml
    python check_userskill.py output/plik.xml --source source/plik.xml
    python check_userskill.py output/plik.xml --report raport.txt
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

from translate_userskill import (
    CREDIT,
    FORBIDDEN_ES,
    KEEP_ENGLISH,
    ORPHAN_TAG_RE,
    describe_problems,
    engine_vars,
    looks_untranslated,
)

SEPARATOR = "<br>[ES]"
CREDIT_MARK = f"<br><font color='#555555'>{CREDIT}"
ATTRS_TO_KEEP = ("id", "name", "gender", "race", "class")


def load_entries(path: Path) -> list[dict[str, str]]:
    """Lista wpisow w kolejnosci pliku. Klucz id|class|index, bo id sie powtarza."""
    root = ET.parse(path).getroot()
    entries: list[dict[str, str]] = []
    for index, element in enumerate(root):
        identifier = element.get("id") or ""
        cls = element.get("class") or ""
        entries.append(
            {
                "key": f"{identifier}|{cls}|{index}",
                "id": identifier,
                "name": element.get("name") or "",
                "gender": element.get("gender") or "",
                "race": element.get("race") or "",
                "class": cls,
                "tooltip": element.get("tooltip") or "",
            }
        )
    return entries


def split_halves(tooltip: str) -> tuple[str, str] | None:
    """Rozdziela tooltip na czesc angielska i hiszpanska."""
    if SEPARATOR not in tooltip:
        return None
    english, rest = tooltip.split(SEPARATOR, 1)
    english = english.replace("[EN] ", "", 1)
    spanish = rest.split(CREDIT_MARK)[0]
    return english, spanish


def normalize(text: str) -> str:
    return " ".join(html.unescape(text).split())


def strip_font(text: str) -> str:
    """Tekst bez znacznikow <font>, do porownan odpornych na ich naprawe."""
    plain = html.unescape(text)
    return " ".join(re.sub(r"</?font[^>]*>", "", plain, flags=re.I).split())


def font_balance(text: str) -> int:
    plain = html.unescape(text)
    return len(re.findall(r"<font\b", plain, re.I)) - len(
        re.findall(r"</font\b", plain, re.I)
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sprawdza jakosc przetlumaczonego StrSheet_UserSkill."
    )
    parser.add_argument("translated", help="Plik wynikowy do sprawdzenia")
    parser.add_argument(
        "--source",
        default=None,
        help="Plik zrodlowy (domyslnie zgadywany z nazwy: bez _Translated, w source/)",
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
    # Kolejnosc atrybutow w zrodle: id, name, gender, race, tooltip, class.
    raw_tooltips = {
        f"{m.group(1)}|{m.group(3)}|{i}": m.group(2)
        for i, m in enumerate(
            re.finditer(
                r'<String\b[^>]*\bid="([^"]*)"[^>]*\btooltip="([^"]*)"[^>]*\bclass="([^"]*)"',
                raw,
            )
        )
    }

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

    source_entries: list[dict[str, str]] = []
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

        if len(source_entries) != len(entries):
            add(
                "liczba wpisow",
                f"{len(source_entries)} -> {len(entries)}",
            )
            print(
                f"Wpisy: zrodlo {len(source_entries)}, wynik {len(entries)} -> ROZNICA"
            )
        else:
            print(f"Wpisy: {len(entries)} (kolejnosc 1:1 ze zrodlem)")

        pair_count = min(len(source_entries), len(entries))
        for src, dst in zip(source_entries[:pair_count], entries[:pair_count]):
            for attr in ATTRS_TO_KEEP:
                if src[attr] != dst[attr]:
                    add(
                        f"zmieniony atrybut {attr}",
                        f'{src["key"]}: "{src[attr]}" -> "{dst[attr]}"',
                    )
    else:
        print(f"(pomijam porownanie ze zrodlem - nie znaleziono {source_path})")

    non_ascii = sorted({c for c in raw if ord(c) > 127})
    if non_ascii:
        add("znaki spoza ASCII", "".join(non_ascii[:20]))
    print(
        f"Czysty ASCII: {'tak' if not non_ascii else 'NIE (' + str(len(non_ascii)) + ' roznych znakow)'}"
    )
    if "&amp;#" in raw:
        add("podwojne escapowanie", "wystepuje &amp;# zamiast &#")

    counts = {"puste": 0, "przetlumaczone": 0, "bez [ES]": 0}
    source_by_key = {entry["key"]: entry for entry in source_entries}

    for entry in entries:
        identifier = entry["key"]
        tooltip = entry["tooltip"]
        if not tooltip:
            counts["puste"] += 1
            continue

        if ORPHAN_TAG_RE.search(tooltip):
            add("resztki placeholderow", identifier)
        raw_value = raw_tooltips.get(identifier)
        if raw_value is not None and re.search(r"[\r\n]", raw_value):
            add("znak nowej linii w tooltipie", identifier)
        if tooltip.count("[EN]") > 1:
            add("podwojne [EN]", identifier)
        if font_balance(tooltip) != 0:
            add("niezbalansowany <font>", f"{identifier} ({font_balance(tooltip):+d})")

        halves = split_halves(tooltip)
        if halves is None:
            counts["bez [ES]"] += 1
            continue
        counts["przetlumaczone"] += 1
        english, spanish = halves

        if engine_vars(english) != engine_vars(spanish):
            problems_list = describe_problems(english, spanish)
            add(
                "rozjechane zmienne silnika",
                f"{identifier}: {problems_list[0] if problems_list else 'mismatch'}",
            )
        if looks_untranslated(english, spanish):
            add("zdanie zostawione po angielsku", identifier)

        plain_es = html.unescape(spanish)
        for term in KEEP_ENGLISH:
            pattern = r"\b" + re.escape(term)
            if re.search(pattern, html.unescape(english), re.I) and not re.search(
                pattern, plain_es, re.I
            ):
                add(f"zgubiony termin {term}", identifier)
        for forbidden in FORBIDDEN_ES:
            found = re.search(forbidden, plain_es, re.I)
            if found:
                add(f"zakazane slowo {found.group(0)}", identifier)

        original_entry = source_by_key.get(identifier)
        original = original_entry["tooltip"] if original_entry else ""
        if original and "[ES]" not in original and normalize(original) != normalize(english):
            if strip_font(original) == strip_font(english):
                info["naprawiony <font> w czesci [EN]"] = (
                    info.get("naprawiony <font> w czesci [EN]", 0) + 1
                )
            else:
                add("czesc [EN] nie zgadza sie ze zrodlem", identifier)

    print(
        f"Tooltipy: {counts['przetlumaczone']} dwujezycznych, "
        f"{counts['bez [ES]']} bez hiszpanskiego, {counts['puste']} pustych"
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
