"""
Translate TERA StrSheet_Item toolTip attributes from English to Spanish
using the Gemini API (google-genai).

Reads the XML line by line with regex so original indentation, attribute
order, and non-toolTip content stay untouched.

Install:
    pip install google-genai

Usage:
    python translate_tooltips.py source/TESTTEST_StrSheet_Item-00011.xml
    python translate_tooltips.py source/file.xml --batch-size 40
    python translate_tooltips.py source/file.xml --limit 300     # test run
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
from pathlib import Path

from google import genai
from google.genai import types, errors
# Model potrafi urwac placeholder (__TAG0) albo wymyslic wlasny (__COLOR_END__).
ORPHAN_TAG_RE = re.compile(r"__TAG\d+(?:__)?|__[A-Z][A-Z0-9_]{2,}__")
PLACEHOLDER_STRIP_RE = re.compile(r"__TAG\d+__")
# Pliki klienta zawieraja pozostalosci z wersji chinskiej, japonskiej
# i koreanskiej. To nieuzywana tresc, nie zrodlo do tlumaczenia.
CJK_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]")
# ---------------------------------------------------------------------------
# Leave empty. The key is read from the GEMINI_API_KEY environment variable
# (GitHub Secrets on Actions, $env:GEMINI_API_KEY locally).
# NEVER paste a real key here - this file goes into a git repository.
# ---------------------------------------------------------------------------
GEMINI_API_KEY = ""
GEMINI_MODEL = "gemini-3.5-flash-lite"

TOOLTIP_RE = re.compile(r'toolTip="([^"]*)"')
TAG_RE = re.compile(r"<[^>]+>")
# Zmienne silnika TERA ($value, $BR, $COLOR_END...). Klient podmienia je na
# liczby i lamania linii, wiec zgubienie jednej = zepsuty tooltip w grze.
# Kolejnosc w alternatywie jest wazna: w zrodle te tokeny wchodza wprost
# w kolejne slowo ($BRAuto, $COLOR_ENDInflicts, $H_W_GOODGlyph).
VAR_RE = re.compile(r"\$(?:COLOR_END|H_[A-Z]_(?:GOOD|BAD)|BR|[a-z][A-Za-z0-9]*)")
MARKUP_RE = re.compile(TAG_RE.pattern + "|" + VAR_RE.pattern + "|\x01")
# Zrodlo lamie linie encja &#xA;. Chronimy ja znakiem sterujacym, zeby
# przetrwala tlumaczenie i czyszczenie, a na koncu wracala jako encja.
NEWLINE_ENTITY_RE = re.compile(r"&#x0*A;|&#0*10;", re.I)
NEWLINE_MARK = "\x01"
RETRY_AFTER_RE = re.compile(r"retry(?:\s+in)?\s+(\d+(?:\.\d+)?)\s*(?:s|sec|seconds)?", re.I)

# Terminy, ktore MUSZA zostac po angielsku rowniez w tekscie hiszpanskim.
# Nazwy przedmiotow w atrybucie string= sa angielskie, wiec gracz szukajacy
# "Prime Battle Solution" ma znalezc to samo w opisie i w plecaku.
KEEP_ENGLISH = (
    "MP", "HP", "Feedstock", "Battle Solution", "Spellbind", "Alkahest",
    "Noctenium", "Everful Nostrum", "Etching", "Crystal", "Emerald",
    "Diamond", "Talent", "emote",
)
# Slowa, ktore nie moga pojawic sie po hiszpanskiej stronie.
# Odbiorca to gracze z Ameryki Lacinskiej, wiec odpadaja regionalizmy
# z Hiszpanii, a "coger" jest w wiekszosci Latam wulgarne.
FORBIDDEN_ES = (
    r"\bPH\b", r"\baguante\b", r"\btimes\b",
    r"\bcog(?:er|e|es|ed|ido|iendo)\b", r"\bamericana\b", r"\bgafas\b",
    r"\bvosotros\b", r"\bordenador", r"\bzumo\b",
)

# Naglowki opisowe podmieniamy sami, po tlumaczeniu. To zwykle zastapienie
# tekstu, wiec nie ma po co prosic o to modelu - i nie da sie tego zepsuc.
# Nazwy slotow, emotek, questow i przedmiotow NIE sa tu wymienione,
# wiec zostaja po angielsku.
HEADINGS_ES = {
    "[Effect]": "[Efecto]",
    "[Effects]": "[Efectos]",
    "[Duration]": "[Duraci\u00f3n]",
    "[Potion]": "[Poci\u00f3n]",
    "[Note]": "[Nota]",
    "[Rewards]": "[Recompensas]",
    "[Items]": "[Objetos]",
    "[Abilities]": "[Habilidades]",
    "[License]": "[Licencia]",
    "[Caution]": "[Precauci\u00f3n]",
    "[Warning]": "[Advertencia]",
    "[Usage]": "[Uso]",
    "[Source]": "[Origen]",
    "[Battle Dish]": "[Plato de combate]",
}

CREDIT = "Transcription by TERA New Xenesis 2026"
BATCH_SIZE = 100
# Darmowy limit to 15 zapytan na minute; 9s daje zapas takze na naprawy,
# ktore ida po jednym tekscie.
BATCH_DELAY = 9.0

SYSTEM_PROMPT = """
You are an expert video game localizer. Translate TERA MMORPG item tooltips from English to Spanish.

Understand gaming terminology and localize it in context, including drops, loot, buffs, debuffs, slots, and equipping.
Keep the tone appropriate for a high fantasy universe.
Translate meaning naturally; prefer established Spanish MMO phrasing over literal calques.
Keep proper names (Kelsaik, Valkyon, Bahaar, Kaia, Elin, Castanic, Popori, Baraka, Amani, etc.) unchanged unless a well-known Spanish TERA name already exists.
Anything inside square brackets is copied in English exactly as written - equipment slots, menu paths, emote names, quest names and item names all appear in brackets and the player must find them in an English interface.
Preserve numbers, percentages, and UI labels.
Placeholders like __TAG0__, __TAG1__, __TAG2__ are protected markup and game variables. Copy EVERY one of them into the Spanish text, in the same relative positions, with the exact same numbers. Never translate, merge, renumber or delete them. The output must contain exactly the same placeholders as the input, no more and no fewer.
GLOSSARY - follow it exactly, it overrides your own preferences:
- Keep these words in English, spelled exactly as in the source, even inside Spanish sentences: MP, HP, Feedstock, Battle Solution, Spellbind, Alkahest, Noctenium, Everful Nostrum, Etching, Crystal, Emerald, Diamond, Talent. The in-game item list is in English, so players must be able to match them.
- Never write PM, PH or "mana" for MP. Never write PV or PS for HP.
- Endurance is always "resistencia". Never "aguante".
- Power is "poder". Crit Power is "poder de golpe critico".
- "times" as a multiplier is "veces" - never leave the English word.
- Use the Spanish decimal comma: +1,42 not +1.42.
- The audience is Latin American, not Spain. Write neutral Latin American Spanish: address the player as "tu", never use "vosotros" or its verb forms, and avoid Spain-only vocabulary. Use "lentes" not "gafas", "saco" or "blazer" not "americana", "computadora" not "ordenador".
- Never use the verb "coger" in any form - it is vulgar in most of Latin America. Use "tomar", "agarrar", "recoger" or "conseguir" instead.
- Item and material names that are not in the list above are still proper names: keep them in English rather than inventing a Spanish version.
- The same applies to the names of emotes, skills, quests, dungeons, NPCs and UI menus. Write "el emote Girlfriends", never "el gesto de amigas" - the player has to find them in an English interface.

Do not add explanations, notes, quotes, or extra punctuation that was not implied by the source.
Do not include the English source text in your output.
Translate EVERY sentence. A long tooltip may contain many sentences separated by __TAGn__ line breaks - each one must be rendered in Spanish. Never copy an English sentence unchanged into your output, not even a technical one about MP, cooldowns, percentages or durations.
Never use raw line breaks inside the JSON strings you return.
Return ONLY valid JSON: an array of Spanish strings, same length and order as the input array.
""".strip()

OUTPUT_TEMPLATE = (
    "[EN] {english}"
    "&lt;br&gt;"
    "[ES] {spanish}"
    "&lt;br&gt;"
    "&lt;font color='#555555'&gt;" + CREDIT + "&lt;/font&gt;"
)


def is_already_bilingual(text: str) -> bool:
    """True if this toolTip was already processed by a previous run."""
    return "[ES]" in text or CREDIT in text


def xml_attr_escape(text: str) -> str:
    """Escape characters that would break a double-quoted XML attribute."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


HIGH_DECIMAL_ENTITY_RE = re.compile(r"&(?:amp;)?#(\d+);")


def to_xml_entities(text: str) -> str:
    """ASCII w XML: × -> &#215;. Parser przywraca znak, nazwa w grze zostaje ×."""
    return "".join(c if ord(c) < 128 else f"&#{ord(c)};" for c in text)


def to_tera_html_entities(text: str) -> str:
    """Encje w toolTip, ktore przetrwaja Novadrop.

    Parser XML dekoduje &#241; do UTF-8 jeszcze przed spakowaniem, a klient
    TERA pokazuje wtedy krzaki w HTML (holografica -> holog?Afica).
    Zapisujemy &amp;#241;, zeby po XML w stringu zostalo &#241;, a renderer
    HTML w grze zrobil n-tylde. &#xA; (newline) zostaje bez zmian.
    """
    def repl(match: re.Match[str]) -> str:
        code = int(match.group(1))
        return f"&amp;#{code};" if code >= 128 else match.group(0)

    text = HIGH_DECIMAL_ENTITY_RE.sub(repl, text)
    return "".join(c if ord(c) < 128 else f"&amp;#{ord(c)};" for c in text)


def ascii_safe_line(line: str) -> str:
    """Podwojne encje tylko w toolTip; string= zostaje zwyklym &#nnn;."""
    match = TOOLTIP_RE.search(line)
    if not match:
        return to_xml_entities(line)
    start, end = match.span(1)
    return (
        to_xml_entities(line[:start])
        + to_tera_html_entities(match.group(1))
        + to_xml_entities(line[end:])
    )


def protect_markup(text: str) -> tuple[str, list[str]]:
    """Replace HTML-like tags with placeholders so the translator leaves them alone."""
    tags: list[str] = []

    def repl(match: re.Match[str]) -> str:
        tags.append(match.group(0))
        return f"__TAG{len(tags) - 1}__"

    return MARKUP_RE.sub(repl, text), tags


def restore_markup(text: str, tags: list[str]) -> str:
    for i, tag in enumerate(tags):
        text = text.replace(f"__TAG{i}__", tag)
    return text


def load_cache(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_cache(path: Path, cache: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(cache, ensure_ascii=False, indent=0),
        encoding="utf-8",
    )


def is_translatable(protected: str) -> bool:
    """Czy w tekscie jest cokolwiek do przetlumaczenia na hiszpanski."""
    plain = PLACEHOLDER_STRIP_RE.sub("", protected)
    latin = len(re.findall(r"[A-Za-z]", plain))
    if latin == 0:
        return False  # sam markup, liczby albo pismo azjatyckie
    return len(CJK_RE.findall(plain)) < latin


def purge_bad_cache_entries(cache: dict[str, str]) -> int:
    """Wyrzuca z cache wpisy zepsute przez wczesniejsze przebiegi.

    Chodzi o tlumaczenia, ktore zgubily zmienna silnika albo zawieraja
    resztki placeholderow. Zostana przetlumaczone ponownie - tylko one,
    nie caly plik.
    """
    bad = [k for k, v in cache.items()
           if ORPHAN_TAG_RE.search(v) or not translation_is_valid(k, v)]
    for k in bad:
        del cache[k]
    return len(bad)


def prepare_for_translation(original_attr: str) -> tuple[str, list[str]]:
    guarded = NEWLINE_ENTITY_RE.sub(NEWLINE_MARK, original_attr)
    decoded = html.unescape(guarded)
    return protect_markup(decoded)


def sanitize(text: str) -> str:
    """Usuwa to, co rozbiloby linie XML albo tooltip w grze."""
    text = ORPHAN_TAG_RE.sub("", text)
    text = re.sub(r"[\r\n]+", " ", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def balance_font_tags(text: str) -> str:
    """Domyka nieotwarte <font> i usuwa osierocone </font>.

    Dziala zarowno na surowym tekscie (<font>) jak i na zaescapowanym
    (&lt;font&gt;), bo wywolujemy ja w obu tych momentach.
    """
    # Zrodlo uzywa trzech zapisow tego samego znacznika. Wybieramy ten,
    # ktory faktycznie wystepuje w tekscie - od najbardziej zagniezdzonego.
    lower = text.lower()
    if "&amp;lt;font" in lower:
        lt, gt = "&amp;lt;", "&amp;gt;"
    elif "<font" in lower:
        lt, gt = "<", ">"
    else:
        lt, gt = "&lt;", "&gt;"
    opener = re.escape(lt) + r"font[^<>&]*" + re.escape(gt)
    closer = re.escape(lt) + r"/font\s*" + re.escape(gt)
    out = []
    depth = 0
    for piece in re.split(f"({opener}|{closer})", text, flags=re.I):
        if piece is None:
            continue
        if re.fullmatch(opener, piece, re.I):
            depth += 1
            out.append(piece)
        elif re.fullmatch(closer, piece, re.I):
            if depth == 0:
                continue  # osierocone zamkniecie - wyrzucamy
            depth -= 1
            out.append(piece)
        else:
            out.append(piece)
    return "".join(out) + f"{lt}/font{gt}" * depth


def engine_vars(text: str) -> list[str]:
    return sorted(VAR_RE.findall(html.unescape(text)))


# Angielskie slowa funkcyjne - ich obecnosc odroznia zdanie od nazwy wlasnej.
ENGLISH_STOPWORDS = {
    "the", "of", "by", "you", "your", "is", "are", "with", "when", "for",
    "to", "and", "if", "per", "every", "additional", "this", "that", "can",
    "be", "will", "has", "have", "from", "into", "after", "before", "use",
    "used", "increases", "decreases", "wear", "upon", "while", "during",
}


def _segments(text: str) -> list[str]:
    parts = re.split(r"\$BR|<br\s*/?>", text, flags=re.I)
    return [p.strip() for p in parts if p.strip()]


def _plain_words(segment: str) -> list[str]:
    segment = re.sub(r"<[^>]*>", " ", segment)
    segment = re.sub(r"\$[A-Za-z_][A-Za-z0-9_]*", " ", segment)
    segment = re.sub(r"\[[^\]]*\]", " ", segment)
    segment = re.sub(r"[^A-Za-z ]", " ", segment)
    return segment.lower().split()


def looks_untranslated(original: str, spanish_escaped: str) -> bool:
    """Wykrywa zdania przepisane z angielskiego zamiast przetlumaczonych.

    Model przy dlugich opisach potrafi przetlumaczyc czesc zdan, a reszte
    skopiowac. Zmienne silnika sa wtedy komplet, wiec tamta walidacja tego
    nie lapie. Porownujemy zdanie po zdaniu; identyczne zdanie zawierajace
    angielskie slowa funkcyjne oznacza, ze nie zostalo przetlumaczone.
    Nazwy wlasne ("Exodor Scout Armor Feedstock") tych slow nie maja.
    """
    en = set(_segments(html.unescape(original)))
    es = set(_segments(html.unescape(spanish_escaped)))
    for segment in en & es:
        words = _plain_words(segment)
        if len(words) >= 4 and sum(1 for w in words if w in ENGLISH_STOPWORDS) >= 2:
            return True
    return False


def breaks_glossary(original: str, spanish_escaped: str) -> bool:
    """Sprawdza, czy tlumaczenie trzyma sie ustalonej terminologii."""
    en = html.unescape(original)
    es = html.unescape(spanish_escaped)
    for term in KEEP_ENGLISH:
        pattern = r"\b" + re.escape(term)
        if re.search(pattern, en, re.I) and not re.search(pattern, es, re.I):
            return True
    return any(re.search(p, es, re.I) for p in FORBIDDEN_ES)


def translation_is_valid(original: str, spanish_escaped: str) -> bool:
    """Odrzuca tlumaczenie zepsute: zgubiona zmienna, angielskie zdanie
    albo zlamana terminologia."""
    if engine_vars(original) != engine_vars(spanish_escaped):
        return False
    if looks_untranslated(original, spanish_escaped):
        return False
    return not breaks_glossary(original, spanish_escaped)


def describe_problems(original: str, candidate: str) -> list[str]:
    """Wypisuje konkretne usterki, zeby model wiedzial co poprawic."""
    problems: list[str] = []
    en_vars, es_vars = engine_vars(original), engine_vars(candidate)
    if en_vars != es_vars:
        missing = [v for v in en_vars if es_vars.count(v) < en_vars.count(v)]
        extra = [v for v in es_vars if en_vars.count(v) < es_vars.count(v)]
        if missing:
            problems.append(f"missing game variables: {' '.join(sorted(set(missing)))}")
        if extra:
            problems.append(f"invented game variables: {' '.join(sorted(set(extra)))}")
    en_text, es_text = html.unescape(original), html.unescape(candidate)
    for segment in set(_segments(en_text)) & set(_segments(es_text)):
        words = _plain_words(segment)
        if len(words) >= 4 and sum(1 for w in words if w in ENGLISH_STOPWORDS) >= 2:
            problems.append(f"this sentence is still English: {segment[:120]}")
    for term in KEEP_ENGLISH:
        pattern = r"\b" + re.escape(term)
        if re.search(pattern, en_text, re.I) and not re.search(pattern, es_text, re.I):
            problems.append(f"the term {term} must stay in English and is missing")
    for forbidden in FORBIDDEN_ES:
        found = re.search(forbidden, es_text, re.I)
        if found:
            problems.append(f"the word {found.group(0)} is not allowed - see the glossary")
    return problems


def finalize_translation(translated: str, tags: list[str]) -> str:
    restored = restore_markup(translated, tags)
    restored = balance_font_tags(sanitize(restored))
    return xml_attr_escape(restored).replace(NEWLINE_MARK, "&#xA;")


def localize_headings(text: str) -> str:
    """Podmienia angielskie naglowki opisowe na hiszpanskie."""
    for english, spanish in HEADINGS_ES.items():
        text = text.replace(english, spanish)
    return text


def bilingual_tooltip(original_attr: str, spanish_escaped: str) -> str:
    # Dziala takze na wpisy ze starego cache, wiec stare bledy tez sie czyszcza.
    english = balance_font_tags(sanitize(original_attr))
    spanish = localize_headings(balance_font_tags(sanitize(spanish_escaped)))
    return OUTPUT_TEMPLATE.format(english=english, spanish=spanish)


def collect_unique_uncached(lines: list[str], cache: dict[str, str]) -> list[str]:
    unique: list[str] = []
    seen = set(cache.keys())
    for line in lines:
        match = TOOLTIP_RE.search(line)
        if not match:
            continue
        original = match.group(1)
        if original == "" or original in seen:
            continue
        if is_already_bilingual(original):
            continue
        seen.add(original)
        unique.append(original)
    return unique


def resolve_api_key() -> str:
    key = (GEMINI_API_KEY or "").strip()
    if not key:
        key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key or key.upper() in {"YOUR_API_KEY_HERE", "PASTE_YOUR_KEY_HERE"}:
        raise SystemExit(
            "GEMINI_API_KEY is not set. On GitHub Actions add it under "
            "Settings > Secrets and variables > Actions."
        )
    return key


def build_client() -> genai.Client:
    return genai.Client(api_key=resolve_api_key())


def build_config() -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        temperature=0.0,
        response_mime_type="application/json",
        safety_settings=[
            types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
            types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
            types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
            types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
        ],
    )


def build_user_prompt(texts: list[str]) -> str:
    payload = json.dumps(texts, ensure_ascii=False)
    return (
        "Translate this JSON array of English TERA item tooltips into Spanish.\n"
        "Return a JSON array of Spanish strings with the same length and order.\n"
        "Preserve every __TAGn__ placeholder exactly.\n\n"
        f"{payload}"
    )


def parse_translation_array(raw: str, expected: int) -> list[str]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text, strict=False)
    if isinstance(data, dict):
        for key in ("translations", "results", "items"):
            if key in data:
                data = data[key]
                break
    if not isinstance(data, list) or len(data) != expected:
        got = len(data) if isinstance(data, list) else type(data).__name__
        raise RuntimeError(f"Gemini JSON size mismatch: expected {expected} strings, got {got}")
    return [str(item) for item in data]


def is_rate_limit_error(exc: Exception) -> bool:
    if isinstance(exc, errors.ClientError) and getattr(exc, "code", None) == 429:
        return True
    text = str(exc).lower()
    return any(
        token in text
        for token in (
            "429",
            "resource exhausted",
            "resource_exhausted",
            "too many requests",
            "rate limit",
            "quota",
        )
    )


def rate_limit_wait_seconds(exc: Exception, attempt: int) -> int:
    match = RETRY_AFTER_RE.search(str(exc))
    if match:
        return max(int(float(match.group(1))) + 1, 5)
    return min(45 * attempt, 240)


def extract_response_text(response: object) -> str:
    text = getattr(response, "text", None)
    if text:
        return str(text)
    raise RuntimeError(f"Gemini returned no text (blocked or empty): {response!r}")


def translate_batch_with_retry(
    client: genai.Client,
    texts: list[str],
    retries: int = 6,
) -> list[str]:
    last_error: Exception | None = None
    prompt = build_user_prompt(texts)
    for attempt in range(1, retries + 1):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=build_config(),
            )
            return parse_translation_array(extract_response_text(response), len(texts))
        except Exception as exc:  # noqa: BLE001 - network/API failures are expected
            last_error = exc
            if is_rate_limit_error(exc):
                wait = rate_limit_wait_seconds(exc, attempt)
                print(
                    f"    Gemini rate/quota limit on attempt {attempt}/{retries}; "
                    f"sleeping {wait}s",
                    flush=True,
                )
            else:
                wait = min(2 ** attempt, 30)
                print(
                    f"    retry {attempt}/{retries} after error: {exc} (sleep {wait}s)",
                    flush=True,
                )
            time.sleep(wait)
    raise RuntimeError(f"Batch translation failed after {retries} retries: {last_error}")


def translate_chunk(
    client: genai.Client,
    originals: list[str],
    rejected: list[tuple[str, str]] | None = None,
) -> dict[str, str]:
    """Translate one chunk. On persistent failure, split the chunk and retry."""
    if not originals:
        return {}

    results: dict[str, str] = {}
    prepared_texts: list[str] = []
    tags_by_index: list[list[str]] = []
    to_translate: list[str] = []
    for original in originals:
        protected, tags = prepare_for_translation(original)
        if not is_translatable(protected):
            # Sam markup, liczby albo tekst chinski/koreanski. Wyslanie tego
            # do modelu konczy sie pusta odpowiedzia i seria ponowien.
            results[original] = finalize_translation(protected, tags)
            continue
        to_translate.append(original)
        prepared_texts.append(protected)
        tags_by_index.append(tags)
    originals = to_translate
    if not originals:
        return results

    try:
        translated = translate_batch_with_retry(client, prepared_texts)
    except Exception as exc:  # noqa: BLE001
        if len(originals) == 1:
            print(f"  WARNING: giving up on one string ({exc})", flush=True)
            return {}
        mid = len(originals) // 2
        print(
            f"  batch of {len(originals)} failed ({exc}); "
            f"splitting into {mid} + {len(originals) - mid}",
            flush=True,
        )
        merged = translate_chunk(client, originals[:mid], rejected)
        time.sleep(BATCH_DELAY)
        merged.update(translate_chunk(client, originals[mid:], rejected))
        return merged

    bad = 0
    for original, spanish, tags in zip(originals, translated, tags_by_index):
        if not spanish.strip():
            # Model nic nie odeslal dla tego tekstu. Zamiast wysadzac cala
            # paczke, kierujemy ten jeden do naprawy.
            bad += 1
            if rejected is not None:
                rejected.append((original, original))
            continue
        candidate = finalize_translation(spanish, tags)
        if not translation_is_valid(original, candidate):
            bad += 1
            if rejected is not None:
                rejected.append((original, candidate))
            continue  # nie trafia do cache; runda poprawkowa sprobuje ponownie
        results[original] = candidate
    if bad:
        print(f"    rejected {bad} translation(s): engine variables lost", flush=True)
    return results


def repair_one(client: genai.Client, original: str, bad_candidate: str) -> str | None:
    """Prosi model o poprawienie konkretnej wpadki, zamiast slepo powtarzac."""
    protected, tags = prepare_for_translation(original)
    problems = describe_problems(original, bad_candidate)
    prompt = (
        "Your previous Spanish translation of this TERA tooltip was rejected.\n\n"
        f"SOURCE (English, with __TAGn__ placeholders):\n{protected}\n\n"
        f"YOUR REJECTED ATTEMPT:\n{html.unescape(bad_candidate)}\n\n"
        "PROBLEMS TO FIX:\n- " + "\n- ".join(problems) + "\n\n"
        "Fix every problem listed above and keep everything that was already "
        "correct. Return ONLY a JSON array with exactly one Spanish string."
    )
    for attempt in range(1, 4):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL, contents=prompt, config=build_config()
            )
            fixed = parse_translation_array(extract_response_text(response), 1)[0]
            candidate = finalize_translation(fixed, tags)
            if translation_is_valid(original, candidate):
                return candidate
            bad_candidate = candidate
            problems = describe_problems(original, candidate)
        except Exception as exc:  # noqa: BLE001
            if is_rate_limit_error(exc):
                time.sleep(rate_limit_wait_seconds(exc, attempt))
            else:
                time.sleep(min(2 ** attempt, 20))
        time.sleep(BATCH_DELAY)
    return None


def fill_cache_in_batches(
    unique_originals: list[str],
    client: genai.Client,
    cache: dict[str, str],
    cache_path: Path,
    batch_size: int,
) -> int:
    total = len(unique_originals)
    if total == 0:
        print("All non-empty toolTips are already in the cache.")
        return 0

    batch_count = (total + batch_size - 1) // batch_size
    translated_count = 0
    rejected: list[tuple[str, str]] = []
    print(
        f"Translating {total} unique toolTips with {GEMINI_MODEL} "
        f"in {batch_count} batches of up to {batch_size}...",
        flush=True,
    )

    for batch_index in range(batch_count):
        start = batch_index * batch_size
        chunk = unique_originals[start : start + batch_size]
        print(f"  batch {batch_index + 1}/{batch_count} ({len(chunk)} strings)", flush=True)
        new_entries = translate_chunk(client, chunk, rejected)
        cache.update(new_entries)
        translated_count += len(new_entries)
        save_cache(cache_path, cache)
        missing = len(chunk) - len(new_entries)
        if missing:
            print(f"    cached {len(new_entries)}, skipped {missing}", flush=True)
        if batch_index + 1 < batch_count:
            time.sleep(BATCH_DELAY)

    # Naprawa z informacja zwrotna: model dostaje swoja nieudana probe
    # i konkretna liste usterek. Wolniej niz slepe powtorzenie, ale skuteczniej.
    if rejected:
        print(f"  naprawa {len(rejected)} odrzuconych tekstow, po jednym", flush=True)
        still_bad = 0
        for index, (original, bad_candidate) in enumerate(rejected, 1):
            if index % 25 == 0:
                print(f"    naprawiono {index}/{len(rejected)}", flush=True)
            fixed = repair_one(client, original, bad_candidate)
            if fixed is None:
                still_bad += 1
                continue
            cache[original] = fixed
            translated_count += 1
            save_cache(cache_path, cache)
        if still_bad:
            print(f"  {still_bad} tekstow zostaje po angielsku", flush=True)

    return translated_count


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
        match = TOOLTIP_RE.search(line)
        if not match:
            output_lines.append(line)
            stats["no_tooltip"] += 1
            continue

        original = match.group(1)
        if original == "":
            output_lines.append(line)
            stats["empty"] += 1
            continue

        if is_already_bilingual(original):
            output_lines.append(line)
            stats["already_bilingual"] += 1
            continue

        spanish_escaped = cache.get(original)
        if spanish_escaped is None:
            output_lines.append(line)
            stats["left_original"] += 1
            continue

        start, end = match.span(1)
        new_value = bilingual_tooltip(original, spanish_escaped)
        output_lines.append(line[:start] + new_value + line[end:])
        stats["applied"] += 1

    if ascii_safe:
        output_lines = [ascii_safe_line(line) for line in output_lines]

    return output_lines, stats


def process_file(
    input_path: Path,
    output_path: Path,
    cache_path: Path,
    batch_size: int,
    limit: int | None,
    ascii_safe: bool = True,
) -> None:
    cache = load_cache(cache_path)

    with input_path.open("r", encoding="utf-8", newline="") as handle:
        lines = handle.readlines()
    if limit:
        lines = lines[:limit]
    print(f"Reading {input_path.name} ({len(lines)} lines)...", flush=True)
    purged = purge_bad_cache_entries(cache)
    print(f"Cache: {cache_path} ({len(cache)} entries already known)", flush=True)
    if purged:
        print(f"  purged {purged} broken cache entries - they will be retranslated", flush=True)

    unique_originals = collect_unique_uncached(lines, cache)
    if unique_originals:
        client = build_client()
        new_translations = fill_cache_in_batches(
            unique_originals, client, cache, cache_path, batch_size
        )
    else:
        new_translations = 0
        print("All non-empty toolTips are already in the cache.", flush=True)

    output_lines, stats = rewrite_lines(lines, cache, ascii_safe)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        handle.writelines(output_lines)
    save_cache(cache_path, cache)

    print()
    print(f"Wrote {output_path}")
    print(f"  new API translations : {new_translations}")
    print(f"  bilingual toolTips   : {stats['applied']}")
    print(f"  already bilingual    : {stats['already_bilingual']}")
    print(f"  empty toolTip skipped: {stats['empty']}")
    print(f"  lines without toolTip: {stats['no_tooltip']}")
    print(f"  left untranslated    : {stats['left_original']}")


def process_files(
    input_paths: list[Path],
    output_dir: Path,
    cache_path: Path,
    batch_size: int,
    ascii_safe: bool = True,
) -> None:
    """Tlumaczy wiele plikow na jednym cache i jednym przebiegu Gemini."""
    if not input_paths:
        print("No XML files to translate.", flush=True)
        return

    cache = load_cache(cache_path)
    print(f"Cache: {cache_path} ({len(cache)} entries already known)", flush=True)
    purged = purge_bad_cache_entries(cache)
    if purged:
        print(f"  purged {purged} broken cache entries - they will be retranslated", flush=True)

    loaded: list[tuple[Path, list[str]]] = []
    unique: list[str] = []
    seen = set(cache.keys())
    for input_path in input_paths:
        with input_path.open("r", encoding="utf-8", newline="") as handle:
            lines = handle.readlines()
        loaded.append((input_path, lines))
        for original in collect_unique_uncached(lines, cache):
            if original in seen:
                continue
            seen.add(original)
            unique.append(original)

    print(
        f"Folder: {len(loaded)} files, {len(unique)} unique strings missing from cache",
        flush=True,
    )
    if unique:
        client = build_client()
        new_translations = fill_cache_in_batches(
            unique, client, cache, cache_path, batch_size
        )
    else:
        new_translations = 0
        print("All non-empty strings are already in the cache.", flush=True)

    output_dir.mkdir(parents=True, exist_ok=True)
    totals = {
        "applied": 0,
        "already_bilingual": 0,
        "empty": 0,
        "no_tooltip": 0,
        "left_original": 0,
    }
    for input_path, lines in loaded:
        output_path = output_dir / f"{input_path.stem}_Translated{input_path.suffix}"
        output_lines, stats = rewrite_lines(lines, cache, ascii_safe)
        with output_path.open("w", encoding="utf-8", newline="") as handle:
            handle.writelines(output_lines)
        for key in totals:
            totals[key] += stats[key]
        print(f"Wrote {output_path}", flush=True)

    save_cache(cache_path, cache)
    print()
    print(f"Pack done ({len(loaded)} files)")
    print(f"  new API translations : {new_translations}")
    print(f"  bilingual strings    : {totals['applied']}")
    print(f"  already bilingual    : {totals['already_bilingual']}")
    print(f"  empty skipped        : {totals['empty']}")
    print(f"  left untranslated    : {totals['left_original']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Translate TERA item toolTips to bilingual EN/ES via Gemini."
    )
    parser.add_argument("input_xml", help="Source StrSheet XML file")
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output XML path (default: output/<name>_Translated.xml)",
    )
    parser.add_argument(
        "--cache",
        default="cache/tooltip_translation_cache.json",
        help="Shared translation cache (default: cache/tooltip_translation_cache.json)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE,
        help=f"Unique toolTips per Gemini request (default: {BATCH_SIZE})",
    )
    parser.add_argument(
        "--no-ascii-entities",
        action="store_true",
        help="Zapisz akcenty jako zwykle znaki UTF-8 zamiast encji &#nnn;",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Only process the first N lines - useful for a cheap test run",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input_xml).expanduser()
    if not input_path.is_file():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        return 1

    if args.output:
        output_path = Path(args.output).expanduser()
    else:
        output_path = Path("output") / f"{input_path.stem}_Translated{input_path.suffix}"

    cache_path = Path(args.cache).expanduser()
    batch_size = args.batch_size if args.batch_size > 0 else BATCH_SIZE
    limit = args.limit if args.limit > 0 else None

    process_file(
        input_path, output_path, cache_path, batch_size, limit, not args.no_ascii_entities
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
