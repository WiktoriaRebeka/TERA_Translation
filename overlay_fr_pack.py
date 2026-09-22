"""
Build the live pack for the French DataCenter skeleton.

Existing Spanish (QuestDialog, VillagerDialog, …) is remapped by
(id, huntingZoneId), not filename. Proper names come from the EN dump.
Quest / Item / UserSkill Spanish is extracted from GitHub bilingual output
and written into the French file layout.

Does not touch TERA_DATABASE_FRA. Writes to TERA_DATABASE_TRANSLATION.
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

from extract_spanish import extract_string_value

FR = Path(r"C:\Users\wikto\Desktop\TERA_DATABASE_FRA\outputfrances\output\DataCenter_Final_EUR")
EN = Path(r"C:\Users\wikto\Desktop\TERA BAZA DANYCH\Output\Output\DataCenter_Final_EUR")
PACK = Path(r"C:\Users\wikto\Desktop\TERA_DATABASE_TRANSLATION")
GIT_OUT = Path(r"C:\Users\wikto\Desktop\TERA_Translation\output")

ROOT_ID_RE = re.compile(
    r"<(QuestDialog|VillagerDialog)\b([^>]*)>",
    re.DOTALL,
)
ATTR_RE = re.compile(r'\b(id|huntingZoneId)="(\d+)"')
STRING_ID_RE = re.compile(r'\bid="(\d+)"')
CLASS_RE = re.compile(r'\bclass="([^"]*)"')
READABLE_RE = re.compile(r'\breadableId="([^"]+)"')


def xml_files(folder: Path) -> list[Path]:
    files = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix == ".xml")
    xmlxml = sorted(p for p in folder.iterdir() if p.name.endswith(".xml.xml"))
    return files or xmlxml


def parse_dialog_key(path: Path) -> tuple[str, str] | None:
    head = path.read_bytes()[:4000].decode("utf-8", errors="replace")
    match = ROOT_ID_RE.search(head)
    if not match:
        return None
    attrs = dict(ATTR_RE.findall(match.group(2)))
    if "id" not in attrs or "huntingZoneId" not in attrs:
        return None
    return attrs["id"], attrs["huntingZoneId"]


def index_dialogs(folder: Path) -> dict[tuple[str, str], Path]:
    index: dict[tuple[str, str], Path] = {}
    dupes = 0
    for path in xml_files(folder):
        key = parse_dialog_key(path)
        if key is None:
            continue
        if key in index:
            dupes += 1
            continue
        index[key] = path
    if dupes:
        print(f"  skipped {dupes} duplicate keys in {folder.name}", flush=True)
    return index


def swap_dir(dest: Path, built: Path) -> None:
    old = dest.with_name(dest.name + ".__old")
    if old.exists():
        shutil.rmtree(old)
    dest.replace(old)
    built.replace(dest)
    shutil.rmtree(old)


def overlay_dialogs(kind: str) -> dict[str, int]:
    es_dir = PACK / kind
    fr_dir = FR / kind
    print(f"\n== {kind}: remap by (id, huntingZoneId) ==", flush=True)
    es_index = index_dialogs(es_dir)
    fr_files = xml_files(fr_dir)
    tmp = PACK / f"__tmp_{kind}"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    used_es = 0
    copied_fr = 0
    missing_key = 0
    for src in fr_files:
        key = parse_dialog_key(src)
        dest = tmp / src.name
        if key and key in es_index:
            shutil.copy2(es_index[key], dest)
            used_es += 1
        else:
            shutil.copy2(src, dest)
            copied_fr += 1
            if key is None:
                missing_key += 1
    swap_dir(es_dir, tmp)
    stats = {
        "fr_files": len(fr_files),
        "es_matched": used_es,
        "fr_passthrough": copied_fr,
        "missing_key": missing_key,
        "es_index": len(es_index),
    }
    print(
        f"  wrote {len(fr_files)} files: {used_es} from ES, "
        f"{copied_fr} FR passthrough (empty/extra)",
        flush=True,
    )
    return stats


def copy_en_sheet(folder: str) -> int:
    src = EN / folder
    dest = PACK / folder
    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    for path in xml_files(src):
        name = path.name.replace(".xml.xml", ".xml")
        shutil.copy2(path, dest / name)
        count += 1
    print(f"  {folder}: copied {count} EN xml -> pack", flush=True)
    return count


def iter_translated(paths: list[Path]):
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if "String" not in line or 'id="' not in line:
                continue
            yield line


def set_attr(line: str, attr: str, value: str) -> str:
    pattern = re.compile(rf'\b{attr}="[^"]*"')
    if pattern.search(line):
        return pattern.sub(lambda _m: f'{attr}="{value}"', line, count=1)
    return line


def overlay_systemmessage() -> dict[str, int]:
    print("\n== StrSheet_SystemMessage: ES from GitHub into FR files (else EN) ==", flush=True)
    es_by_id: dict[str, str] = {}
    git_dir = GIT_OUT / "StrSheet_SystemMessage"
    git_files = xml_files(git_dir) if git_dir.is_dir() else []
    for path in git_files:
        for line in path.read_text(encoding="utf-8").splitlines():
            ident = READABLE_RE.search(line)
            match = re.search(r'\bstring="([^"]*)"', line)
            if ident and match and match.group(1):
                es_by_id[ident.group(1)] = extract_string_value(match.group(1))
    if not es_by_id:
        copy_en_sheet("StrSheet_SystemMessage")
        return {"applied": 0, "fallback": "en"}

    dest_dir = PACK / "StrSheet_SystemMessage"
    dest_dir.mkdir(parents=True, exist_ok=True)
    applied = leftover = 0
    files = xml_files(FR / "StrSheet_SystemMessage")
    for src in files:
        raw = src.read_bytes()
        newline = b"\r\n" if b"\r\n" in raw[:400] else b"\n"
        text = raw.decode("utf-8")
        out_lines: list[str] = []
        for line in text.splitlines(keepends=True):
            ident = READABLE_RE.search(line)
            if ident and ident.group(1) in es_by_id:
                line = set_attr(line, "string", es_by_id[ident.group(1)])
                applied += 1
            elif ident:
                leftover += 1
            out_lines.append(line)
        out = "".join(out_lines).encode("utf-8")
        if newline == b"\r\n":
            out = out.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        (dest_dir / src.name).write_bytes(out)
    print(f"  applied {applied} leftover {leftover}", flush=True)
    return {"applied": applied, "leftover": leftover, "files": len(files)}


def overlay_quest() -> dict[str, int]:
    print("\n== StrSheet_Quest: extract GitHub ES into FR files ==", flush=True)
    es_by_id: dict[str, str] = {}
    for line in iter_translated(xml_files(GIT_OUT / "StrSheet_Quest")):
        mid = STRING_ID_RE.search(line)
        mstr = re.search(r'\bstring="([^"]*)"', line)
        if not mid or not mstr:
            continue
        spanish = extract_string_value(mstr.group(1))
        es_by_id[mid.group(1)] = spanish

    dest_dir = PACK / "StrSheet_Quest"
    dest_dir.mkdir(parents=True, exist_ok=True)
    applied = 0
    leftover_fr = 0
    empty = 0
    files = xml_files(FR / "StrSheet_Quest")
    for src in files:
        out_lines: list[str] = []
        raw = src.read_bytes()
        newline = b"\r\n" if b"\r\n" in raw[:400] else b"\n"
        text = raw.decode("utf-8")
        for line in text.splitlines(keepends=True):
            if "<String" in line and 'id="' in line:
                mid = STRING_ID_RE.search(line)
                mstr = re.search(r'\bstring="([^"]*)"', line)
                if mid and mstr:
                    qid = mid.group(1)
                    if qid in es_by_id:
                        line = set_attr(line, "string", es_by_id[qid])
                        applied += 1
                    elif not mstr.group(1):
                        empty += 1
                    else:
                        leftover_fr += 1
            out_lines.append(line)
        out = "".join(out_lines).encode("utf-8")
        if newline == b"\r\n":
            out = out.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        (dest_dir / src.name).write_bytes(out)
    print(
        f"  FR files {len(files)}, ES ids {len(es_by_id)}, "
        f"applied {applied}, leftover FR {leftover_fr}, empty {empty}",
        flush=True,
    )
    return {
        "files": len(files),
        "es_ids": len(es_by_id),
        "applied": applied,
        "leftover_fr": leftover_fr,
        "empty": empty,
    }


def overlay_item() -> dict[str, int]:
    print("\n== StrSheet_Item: EN names + ES tooltips into FR files ==", flush=True)
    names: dict[str, str] = {}
    tips: dict[str, str] = {}
    item_paths = sorted(GIT_OUT.glob("StrSheet_Item-*_Translated.xml"))
    for line in iter_translated(item_paths):
        mid = STRING_ID_RE.search(line)
        mname = re.search(r'\bstring="([^"]*)"', line)
        mtip = re.search(r'\btoolTip="([^"]*)"', line)
        if not mid:
            continue
        iid = mid.group(1)
        if mname:
            names[iid] = extract_string_value(mname.group(1), keep_english=True)
        if mtip:
            tips[iid] = extract_string_value(mtip.group(1))

    dest_dir = PACK / "StrSheet_Item"
    dest_dir.mkdir(parents=True, exist_ok=True)
    name_n = tip_n = leftover = 0
    files = xml_files(FR / "StrSheet_Item")
    for src in files:
        raw = src.read_bytes()
        newline = b"\r\n" if b"\r\n" in raw[:400] else b"\n"
        text = raw.decode("utf-8")
        out_lines: list[str] = []
        for line in text.splitlines(keepends=True):
            if "<String" in line and 'id="' in line:
                mid = STRING_ID_RE.search(line)
                if mid:
                    iid = mid.group(1)
                    if iid in names:
                        line = set_attr(line, "string", names[iid])
                        name_n += 1
                    if iid in tips:
                        line = set_attr(line, "toolTip", tips[iid])
                        tip_n += 1
                    elif iid not in names:
                        leftover += 1
            out_lines.append(line)
        out = "".join(out_lines).encode("utf-8")
        if newline == b"\r\n":
            out = out.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        (dest_dir / src.name).write_bytes(out)
    print(
        f"  names {name_n}, tooltips {tip_n}, ids without GitHub {leftover}",
        flush=True,
    )
    return {"names": name_n, "tooltips": tip_n, "leftover": leftover, "files": len(files)}


def overlay_userskill() -> dict[str, int]:
    print("\n== StrSheet_UserSkill: EN names + ES tooltips into FR files ==", flush=True)
    names: dict[tuple[str, str], str] = {}
    tips: dict[tuple[str, str], str] = {}
    paths = sorted(GIT_OUT.glob("StrSheet_UserSkill-*_Translated.xml"))
    for line in iter_translated(paths):
        mid = STRING_ID_RE.search(line)
        mclass = CLASS_RE.search(line)
        mname = re.search(r'\bname="([^"]*)"', line)
        mtip = re.search(r'\btooltip="([^"]*)"', line)
        if not mid:
            continue
        key = (mid.group(1), mclass.group(1) if mclass else "")
        if mname:
            names[key] = extract_string_value(mname.group(1), keep_english=True)
        if mtip:
            tips[key] = extract_string_value(mtip.group(1))

    dest_dir = PACK / "StrSheet_UserSkill"
    dest_dir.mkdir(parents=True, exist_ok=True)
    name_n = tip_n = leftover = 0
    files = xml_files(FR / "StrSheet_UserSkill")
    for src in files:
        raw = src.read_bytes()
        newline = b"\r\n" if b"\r\n" in raw[:400] else b"\n"
        text = raw.decode("utf-8")
        out_lines: list[str] = []
        for line in text.splitlines(keepends=True):
            if "<String" in line and 'id="' in line:
                mid = STRING_ID_RE.search(line)
                mclass = CLASS_RE.search(line)
                if mid:
                    key = (mid.group(1), mclass.group(1) if mclass else "")
                    if key in names:
                        line = set_attr(line, "name", names[key])
                        name_n += 1
                    if key in tips:
                        line = set_attr(line, "tooltip", tips[key])
                        tip_n += 1
                    elif key not in names:
                        leftover += 1
            out_lines.append(line)
        out = "".join(out_lines).encode("utf-8")
        if newline == b"\r\n":
            out = out.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        (dest_dir / src.name).write_bytes(out)
    print(
        f"  names {name_n}, tooltips {tip_n}, rows without GitHub {leftover}",
        flush=True,
    )
    return {"names": name_n, "tooltips": tip_n, "leftover": leftover, "files": len(files)}


def verify_samples() -> None:
    print("\n== sample checks ==", flush=True)
    qd = PACK / "QuestDialog" / "QuestDialog-00000.xml"
    if qd.is_file():
        head = qd.read_text(encoding="utf-8", errors="replace")[:500]
        print("  QuestDialog-00000 root:", ROOT_ID_RE.search(head).group(0)[:120] if ROOT_ID_RE.search(head) else "?")
        print("  has Fey Forest" , "Fey Forest" in head, "has Forêt", "Forêt" in head or "For" in head[:400])
    region = PACK / "StrSheet_Region" / "StrSheet_Region-00000.xml"
    if region.is_file():
        text = region.read_text(encoding="utf-8", errors="replace")
        print("  Region id 101 Arun", 'id="101" string="Arun"' in text)
        print("  Region not Le Monde", 'string="Le Monde"' not in text)
        print("  Region The World", 'string="The World"' in text)
    item = PACK / "StrSheet_Item" / "StrSheet_Item-00000.xml"
    if item.is_file():
        text = item.read_text(encoding="utf-8", errors="replace")[:800]
        print("  Item1 name EN", "Velika Midnight Oil" in text)
        print("  Item1 not Huile", "Huile de minuit" not in text)
        print("  Item1 has [ES]?", "[ES]" in text[:800])
    skill = PACK / "StrSheet_UserSkill" / "StrSheet_UserSkill-00000.xml"
    if skill.is_file():
        text = skill.read_text(encoding="utf-8", errors="replace")[:900]
        print("  Skill Convergence", 'name="Convergence"' in text)
        print("  Skill not Rassemblez", "Rassemblez" not in text)
        print("  Skill has [ES]?", "[ES]" in text[:900])
    quest = PACK / "StrSheet_Quest" / "StrSheet_Quest-00000.xml"
    if quest.is_file():
        text = quest.read_text(encoding="utf-8", errors="replace")[:500]
        print("  Quest Accept", "Aceptar" in text, "Accepter" not in text)
        print("  Quest no [EN]", "[EN]" not in text[:500])


def main() -> int:
    if not FR.is_dir() or not EN.is_dir():
        print("Missing FR or EN DataCenter path", file=sys.stderr)
        return 1
    PACK.mkdir(parents=True, exist_ok=True)

    overlay_dialogs("QuestDialog")
    overlay_dialogs("VillagerDialog")

    print("\n== EN proper-name sheets ==", flush=True)
    copy_en_sheet("StrSheet_Region")
    copy_en_sheet("StrSheet_ZoneName")
    copy_en_sheet("StrSheet_Creature")
    overlay_systemmessage()

    overlay_quest()
    overlay_item()
    overlay_userskill()
    verify_samples()
    print("\nDone. Pack:", PACK, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
