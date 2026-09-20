"""
Translate TERA StrSheet_Abnormality buff/debuff tooltips.

name= stays English (Vanguard Valor II). tooltip= bilingual [EN]/[ES], no credit.
StrSheet_AbnormalityKind labels are compact English/Spanish (Benefit/Beneficio).

Usage:
    python translate_abnormality.py source/StrSheet_Abnormality
    python translate_abnormality.py source/StrSheet_AbnormalityKind
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import translate_tooltips as item

ATTR_RE = re.compile(r'\btooltip="([^"]*)"')
KIND_NAME_RE = re.compile(r'\bname="([^"]*)"')
item.TOOLTIP_RE = re.compile(r'\btooltip="([^"]*)"')

item.OUTPUT_TEMPLATE = (
    "[EN] {english}"
    "&lt;br&gt;"
    "[ES] {spanish}"
)


def to_tera_html_entities(text: str) -> str:
    return "".join(c if ord(c) < 128 else f"&amp;#{ord(c)};" for c in text)


item.to_ascii_entities = to_tera_html_entities

# Chrome next to Effect/Efecto. Compact, not [EN]<br>[ES].
KIND_COMPACT = {
    "$H_S_GOODBenefit$COLOR_END": "$H_S_GOODBenefit/Beneficio$COLOR_END",
    "$H_S_GOODSpecial$COLOR_END": "$H_S_GOODSpecial/Especial$COLOR_END",
    "$H_W_GOODSpecial$COLOR_END": "$H_W_GOODSpecial/Especial$COLOR_END",
    "$H_S_BADSpecial$COLOR_END": "$H_S_BADSpecial/Especial$COLOR_END",
    "$H_W_BADSpecial$COLOR_END": "$H_W_BADSpecial/Especial$COLOR_END",
    "$H_S_BADHarmful$COLOR_END": "$H_S_BADHarmful/Perjudicial$COLOR_END",
    "$H_S_BADHarmful$COLOR_END Stun": (
        "$H_S_BADHarmful/Perjudicial$COLOR_END Stun"
    ),
    "$H_S_BADHarmful$COLOR_END Weakening Effect": (
        "$H_S_BADHarmful/Perjudicial$COLOR_END "
        "Weakening Effect/Efecto debilitante"
    ),
    "$H_S_BADHarmful$COLOR_END Periodic Damage": (
        "$H_S_BADHarmful/Perjudicial$COLOR_END "
        "Periodic Damage/Da\u00f1o peri\u00f3dico"
    ),
    "$H_S_BADHarmful$COLOR_END [Stun]": (
        "$H_S_BADHarmful/Perjudicial$COLOR_END [Stun]"
    ),
    "$H_S_BADHarmful$COLOR_END [Weakening Effect]": (
        "$H_S_BADHarmful/Perjudicial$COLOR_END [Weakening Effect]"
    ),
    "$H_S_BADHarmful$COLOR_END [Periodic Damage]": (
        "$H_S_BADHarmful/Perjudicial$COLOR_END [Periodic Damage]"
    ),
    "$H_S_GOODGifted Skill$COLOR_END": (
        "$H_S_GOODGifted Skill/Habilidad otorgada$COLOR_END"
    ),
    "$H_S_GOODPositive$COLOR_END": "$H_S_GOODPositive/Positivo$COLOR_END",
    "$H_S_GOODBonus$COLOR_END": "$H_S_GOODBonus/Bonificaci\u00f3n$COLOR_END",
    "$H_W_GOODRide Benefit$COLOR_END": (
        "$H_W_GOODRide Benefit/Beneficio de montura$COLOR_END"
    ),
    "$H_S_GOODBond Skill$COLOR_END": (
        "$H_S_GOODBond Skill/Habilidad de v\u00ednculo$COLOR_END"
    ),
    "Lucky reward": "Lucky reward/Recompensa de suerte",
}


def collect_unique_uncached(lines: list[str], cache: dict[str, str]) -> list[str]:
    unique: list[str] = []
    seen = set(cache.keys())
    for line in lines:
        for match in ATTR_RE.finditer(line):
            original = match.group(1)
            if original == "" or original in seen:
                continue
            if item.is_already_bilingual(original):
                continue
            seen.add(original)
            unique.append(original)
    return unique


def rewrite_lines(
    lines: list[str],
    cache: dict[str, str],
    ascii_safe: bool = True,
) -> tuple[list[str], dict[str, int]]:
    output_lines: list[str] = []
    stats = {
        "applied": 0,
        "already_bilingual": 0,
        "empty": 0,
        "no_tooltip": 0,
        "left_original": 0,
    }
    for line in lines:
        matches = list(ATTR_RE.finditer(line))
        if not matches:
            output_lines.append(line)
            stats["no_tooltip"] += 1
            continue
        new_line = line
        for match in reversed(matches):
            original = match.group(1)
            if original == "":
                stats["empty"] += 1
                continue
            if item.is_already_bilingual(original):
                stats["already_bilingual"] += 1
                continue
            spanish_escaped = cache.get(original)
            if spanish_escaped is None:
                stats["left_original"] += 1
                continue
            start, end = match.span(1)
            new_value = item.bilingual_tooltip(original, spanish_escaped)
            new_line = new_line[:start] + new_value + new_line[end:]
            stats["applied"] += 1
        output_lines.append(new_line)
    if ascii_safe:
        output_lines = [item.ascii_safe_line(line) for line in output_lines]
    return output_lines, stats


item.collect_unique_uncached = collect_unique_uncached
item.rewrite_lines = rewrite_lines

item.SYSTEM_PROMPT = """
You are an expert video game localizer. Translate TERA MMORPG buff and debuff tooltips from English to Spanish.

These are the body texts of status effects (login buffs, combat buffs, DoTs, stuns). Translate meaning naturally into Latin American Spanish. Keep the combat tone of TERA.
Buff, skill, class, monster and place names stay English: Vanguard Valor, Blessing of Amarun, Bahaar's Blessing, T.E.R.A. TIME, Stand Fast.
Copy every __TAGn__ placeholder and every $token that already appears in that source string, in the same relative position. Never invent extra tokens. If the source has no $value / $value2 / $BR / $COLOR_END / $H_W_GOOD / $H_S_GOOD, the Spanish must not contain any either.
GLOSSARY:
- Keep MP, HP in English. Never PM, PH, mana, PV, PS.
- Endurance is "resistencia". Never "aguante".
- Power is "poder". Crit Power is "poder de golpe critico".
- The English multiplier word "times" becomes "veces".
- Latin American Spanish: "tu", never "vosotros". Never "coger".
- Decimal comma: +1,42 not +1.42.

Do not add explanations. Do not include the English source in your output.
Translate EVERY sentence.
Return ONLY valid JSON: an array of Spanish strings, same length and order as the input array.
""".strip()

DEFAULT_CACHE = "cache/abnormality_translation_cache.json"
CREDIT = item.CREDIT
FORBIDDEN_ES = item.FORBIDDEN_ES
KEEP_ENGLISH = item.KEEP_ENGLISH
describe_problems = item.describe_problems
engine_vars = item.engine_vars
looks_untranslated = item.looks_untranslated


def list_abnormality_files(root: Path, start: int, count: int) -> list[Path]:
    files = sorted(root.glob("StrSheet_Abnormality-*.xml"))
    if start < 0:
        start = 0
    files = files[start:]
    if count > 0:
        files = files[:count]
    return files


def list_kind_files(root: Path) -> list[Path]:
    return sorted(root.glob("StrSheet_AbnormalityKind-*.xml"))


def is_kind_path(path: Path) -> bool:
    name = path.name if path.is_file() else path.name
    return "AbnormalityKind" in name


def rewrite_kind_file(path: Path, output_dir: Path, ascii_safe: bool) -> int:
    raw = path.read_bytes()
    newline = b"\r\n" if b"\r\n" in raw[:200] else b"\n"
    text = raw.decode("utf-8")
    applied = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal applied
        original = match.group(1)
        if original == "" or "/" in original:
            return match.group(0)
        compact = KIND_COMPACT.get(original)
        if compact is None:
            return match.group(0)
        applied += 1
        value = compact
        if ascii_safe:
            value = to_tera_html_entities(value)
        return f'name="{value}"'

    new_text = KIND_NAME_RE.sub(repl, text)
    out = new_text.encode("utf-8")
    if newline == b"\r\n":
        out = out.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    output_dir.mkdir(parents=True, exist_ok=True)
    dest = output_dir / f"{path.stem}_Translated{path.suffix}"
    dest.write_bytes(out)
    return applied


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Translate TERA StrSheet_Abnormality tooltips to bilingual EN/ES."
    )
    parser.add_argument("input_path")
    parser.add_argument("-o", "--output-dir", default="")
    parser.add_argument("--cache", default=DEFAULT_CACHE)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--count", type=int, default=0)
    parser.add_argument("--no-ascii-entities", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input_path).expanduser()
    ascii_safe = not args.no_ascii_entities
    batch_size = args.batch_size if args.batch_size > 0 else 20

    if not input_path.exists():
        print(f"Input not found: {input_path}", file=sys.stderr)
        return 1

    if is_kind_path(input_path):
        files = [input_path] if input_path.is_file() else list_kind_files(input_path)
        if not files:
            print(f"No StrSheet_AbnormalityKind XML in {input_path}", file=sys.stderr)
            return 1
        output_dir = Path(args.output_dir or "output/StrSheet_AbnormalityKind")
        applied = 0
        for path in files:
            applied += rewrite_kind_file(path, output_dir, ascii_safe)
        print(f"Wrote {len(files)} Kind files, compact labels: {applied}", flush=True)
        return 0

    files = [input_path] if input_path.is_file() else list_abnormality_files(
        input_path, args.start, args.count
    )
    if not files:
        print(f"No StrSheet_Abnormality XML in {input_path}", file=sys.stderr)
        return 1
    print(
        f"Pack: {files[0].name} .. {files[-1].name} ({len(files)} files)",
        flush=True,
    )
    output_dir = Path(args.output_dir or "output/StrSheet_Abnormality")
    item.process_files(
        files, output_dir, Path(args.cache).expanduser(), batch_size, ascii_safe
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
