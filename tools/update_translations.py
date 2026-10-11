"""Refresh chattoon/i18n/*.ts from the sources, fill pt_BR and compile .qm files.

Run after changing interface strings:  python tools/update_translations.py
"""

from __future__ import annotations

import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from translations_pt_BR import PLURALS, PT_BR  # noqa: E402

QT_BIN = Path("/usr/lib/qt6/bin")
TS = ROOT / "chattoon" / "i18n" / "chattoon_pt_BR.ts"


def tool(name: str) -> str:
    return str(QT_BIN / name) if (QT_BIN / name).exists() else name


def main() -> int:
    subprocess.run([tool("lupdate"), "chattoon/gui/qml", "chattoon/gui/backend.py", "-extensions", "qml,py",
                    "-ts", str(TS), "-target-language", "pt_BR", "-locations", "none", "-no-obsolete"],
                   cwd=ROOT, check=True, capture_output=True)
    tree = ET.parse(TS)
    missing = []
    for msg in tree.getroot().iter("message"):
        source = msg.find("source").text or ""
        tr = msg.find("translation")
        if msg.get("numerus") == "yes":
            forms = PLURALS.get(source)
            if not forms:
                missing.append(source)
                continue
            for child in list(tr):
                tr.remove(child)
            for form in forms:
                ET.SubElement(tr, "numerusform").text = form
        else:
            text = PT_BR.get(source)
            if text is None:
                missing.append(source)
                continue
            tr.text = text
        tr.attrib.pop("type", None)
    ET.indent(tree)
    tree.write(TS, encoding="utf-8", xml_declaration=True)
    subprocess.run([tool("lrelease"), str(TS), "-qm", str(TS.with_suffix(".qm"))], check=True, capture_output=True)
    if missing:
        print("Untranslated strings:\n  " + "\n  ".join(missing))
        return 1
    print(f"{TS.name}: all strings translated, .qm compiled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
