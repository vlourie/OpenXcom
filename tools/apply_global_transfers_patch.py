#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Apply Global Transfers overview patch to rackrossum/OpenXcom community_build.
Run from repository root.
"""
from __future__ import annotations

import re
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path.cwd()
TOOLS = ROOT / "tools" / "global_transfers"
SRC = ROOT / "src"


def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    print(f"patched: {path}")


def replace_once(path: Path, old: str, new: str) -> None:
    text = read(path)
    if new in text:
        print(f"already patched: {path}")
        return
    if old not in text:
        die(f"pattern not found in {path}: {old[:120]!r}")
    write(path, text.replace(old, new, 1))


def insert_after_once(path: Path, anchor: str, insert: str, marker: str | None = None) -> None:
    text = read(path)
    marker = marker or insert.strip()
    if marker in text:
        print(f"already patched: {path}")
        return
    if anchor not in text:
        die(f"anchor not found in {path}: {anchor!r}")
    write(path, text.replace(anchor, anchor + insert, 1))


def regex_insert_after_once(path: Path, pattern: str, insert: str, marker: str) -> None:
    text = read(path)
    if marker in text:
        print(f"already patched: {path}")
        return
    m = re.search(pattern, text, re.S)
    if not m:
        die(f"regex pattern not found in {path}: {pattern}")
    write(path, text[:m.end()] + insert + text[m.end():])


def copy_new_files() -> None:
    target_dir = SRC / "Basescape"
    target_dir.mkdir(parents=True, exist_ok=True)
    for name in ["GlobalTransfersState.h", "GlobalTransfersState.cpp"]:
        src = TOOLS / name
        if not src.exists():
            die(f"missing patch file: {src}")
        dst = target_dir / name
        shutil.copyfile(src, dst)
        print(f"copied: {dst}")


def patch_cmake() -> None:
    path = SRC / "CMakeLists.txt"
    if not path.exists():
        print("skip: src/CMakeLists.txt not found")
        return
    text = read(path)
    if "Basescape/GlobalTransfersState.cpp" in text:
        print(f"already patched: {path}")
        return
    anchors = [
        "Basescape/GlobalAlienContainmentState.cpp",
        "Basescape/GlobalResearchState.cpp",
        "Basescape/GlobalManufactureState.cpp",
        "Basescape/TransfersState.cpp",
    ]
    for a in anchors:
        if a in text:
            write(path, text.replace(a, a + "\n\tBasescape/GlobalTransfersState.cpp", 1))
            return
    die("could not find a Basescape source anchor in CMakeLists.txt")


def xml_add_vs_item(path: Path, tag_name: str, include_value: str, filter_name: str | None = None) -> None:
    if not path.exists():
        print(f"skip: {path} not found")
        return
    raw = path.read_text(encoding="utf-8-sig")
    if include_value in raw:
        print(f"already patched: {path}")
        return

    try:
        tree = ET.parse(path)
    except Exception as e:
        die(f"cannot parse XML {path}: {e}")

    root = tree.getroot()
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}", 1)[0] + "}"

    # Find an ItemGroup containing same tag, preferably with Basescape items.
    groups = list(root.findall(f"{ns}ItemGroup"))
    target_group = None
    for g in groups:
        for item in g.findall(f"{ns}{tag_name}"):
            if "Basescape\\" in item.attrib.get("Include", ""):
                target_group = g
                break
        if target_group is not None:
            break
    if target_group is None:
        for g in groups:
            if g.find(f"{ns}{tag_name}") is not None:
                target_group = g
                break
    if target_group is None:
        target_group = ET.SubElement(root, f"{ns}ItemGroup")

    item = ET.SubElement(target_group, f"{ns}{tag_name}", {"Include": include_value})
    if filter_name:
        filt = ET.SubElement(item, f"{ns}Filter")
        filt.text = filter_name

    ET.register_namespace('', ns[1:-1] if ns else '')
    tree.write(path, encoding="utf-8", xml_declaration=True)
    print(f"patched XML: {path}")


def patch_visual_studio_projects() -> None:
    xml_add_vs_item(SRC / "OpenXcom.2010.vcxproj", "ClCompile", r"Basescape\GlobalTransfersState.cpp")
    xml_add_vs_item(SRC / "OpenXcom.2010.vcxproj", "ClInclude", r"Basescape\GlobalTransfersState.h")
    xml_add_vs_item(SRC / "OpenXcom.2010.vcxproj.filters", "ClCompile", r"Basescape\GlobalTransfersState.cpp", "Basescape")
    xml_add_vs_item(SRC / "OpenXcom.2010.vcxproj.filters", "ClInclude", r"Basescape\GlobalTransfersState.h", "Basescape")


def patch_options() -> None:
    inc = SRC / "Engine" / "Options.inc.h"
    cpp = SRC / "Engine" / "Options.cpp"
    if not inc.exists() or not cpp.exists():
        die("Options files not found")

    # Options.inc.h: add new variable after keyGeoGlobalAlienContainment.
    text = read(inc)
    if "keyGeoGlobalTransfers" not in text:
        # Works for comma-separated declarations/lists.
        if "keyGeoGlobalAlienContainment," in text:
            text = text.replace("keyGeoGlobalAlienContainment,", "keyGeoGlobalAlienContainment, keyGeoGlobalTransfers,", 1)
        elif "keyGeoGlobalAlienContainment" in text:
            text = text.replace("keyGeoGlobalAlienContainment", "keyGeoGlobalAlienContainment, keyGeoGlobalTransfers", 1)
        else:
            die("keyGeoGlobalAlienContainment not found in Options.inc.h")
        write(inc, text)
    else:
        print(f"already patched: {inc}")

    # Options.cpp: add hotkey option entry in OXCE controls.
    text = read(cpp)
    if "keyGeoGlobalTransfers" not in text or '"keyGeoGlobalTransfers"' not in text:
        line = '\t_info.push_back(OptionInfo(OPTION_OXCE, "keyGeoGlobalTransfers", &keyGeoGlobalTransfers, SDLK_UNKNOWN, "STR_TRANSFER_OVERVIEW", "STR_GEOSCAPE"));\n'
        anchors = [
            'OptionInfo(OPTION_OXCE, "keyGeoGlobalAlienContainment"',
            '"keyGeoGlobalAlienContainment"',
        ]
        inserted = False
        for a in anchors:
            pos = text.find(a)
            if pos != -1:
                eol = text.find('\n', pos)
                if eol == -1:
                    eol = pos
                    # fallback for files minified into one line: insert after next semicolon
                    semi = text.find(';', pos)
                    if semi != -1:
                        eol = semi
                text = text[:eol+1] + line + text[eol+1:]
                inserted = True
                break
        if not inserted:
            die("keyGeoGlobalAlienContainment option not found in Options.cpp")
        write(cpp, text)
    else:
        print(f"already patched: {cpp}")


def patch_geoscape() -> None:
    cpp = SRC / "Geoscape" / "GeoscapeState.cpp"
    h = SRC / "Geoscape" / "GeoscapeState.h"
    if not cpp.exists() or not h.exists():
        die("GeoscapeState files not found")

    insert_after_once(
        cpp,
        '#include "../Basescape/GlobalAlienContainmentState.h"',
        '\n#include "../Basescape/GlobalTransfersState.h"',
        "GlobalTransfersState.h",
    )
    insert_after_once(
        cpp,
        '_btnIntercept->onKeyboardPress((ActionHandler)&GeoscapeState::btnGlobalAlienContainmentClick, Options::keyGeoGlobalAlienContainment);',
        '\n\t_btnIntercept->onKeyboardPress((ActionHandler)&GeoscapeState::btnGlobalTransfersClick, Options::keyGeoGlobalTransfers);',
        "btnGlobalTransfersClick, Options::keyGeoGlobalTransfers",
    )

    function = '''

/**
 * Opens the Global Transfers overview.
 * @param action Pointer to an action.
 */
void GeoscapeState::btnGlobalTransfersClick(Action *)
{
	_game->pushState(new GlobalTransfersState(false));
}
'''
    regex_insert_after_once(
        cpp,
        r"void\s+GeoscapeState::btnGlobalAlienContainmentClick\s*\(\s*Action\s*\*\s*\)\s*\{\s*_game->pushState\(new\s+GlobalAlienContainmentState\(false\)\);\s*\}",
        function,
        "GeoscapeState::btnGlobalTransfersClick",
    )

    insert_after_once(
        h,
        'void btnGlobalAlienContainmentClick(Action *action);',
        '\n\t/// Handler for opening the global transfers overview.\n\tvoid btnGlobalTransfersClick(Action *action);',
        "btnGlobalTransfersClick(Action",
    )


def append_translation(path: Path, key: str, value: str) -> None:
    if not path.exists():
        print(f"skip translation, file not found: {path}")
        return
    text = read(path)
    if f"{key}:" in text:
        print(f"translation exists: {path} {key}")
        return
    if not text.endswith("\n"):
        text += "\n"
    text += f'{key}: "{value}"\n'
    write(path, text)


def patch_translations() -> None:
    append_translation(ROOT / "common" / "Language" / "QOL" / "ru.yml", "STR_TRANSFER_OVERVIEW", "ОБЗОР ВСЕХ ДОСТАВОК")
    append_translation(ROOT / "common" / "Language" / "QOL" / "en-US.yml", "STR_TRANSFER_OVERVIEW", "TRANSFER OVERVIEW")
    append_translation(ROOT / "common" / "Language" / "QOL" / "ru.yml", "STR_BASE_UC", "БАЗА")
    append_translation(ROOT / "common" / "Language" / "QOL" / "en-US.yml", "STR_BASE_UC", "BASE")


def main() -> None:
    if not SRC.exists():
        die("run this script from OpenXcom repository root; src/ not found")
    copy_new_files()
    patch_cmake()
    patch_visual_studio_projects()
    patch_options()
    patch_geoscape()
    patch_translations()
    print("\nGlobal Transfers patch applied.")


if __name__ == "__main__":
    main()
