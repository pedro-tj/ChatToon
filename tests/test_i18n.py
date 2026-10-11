import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TS = ROOT / "chattoon" / "i18n" / "chattoon_pt_BR.ts"


def test_portuguese_translation_is_complete():
    tree = ET.parse(TS)
    unfinished = [m.find("source").text for m in tree.getroot().iter("message")
                  if m.find("translation").get("type") in ("unfinished", "obsolete")
                  or not ((m.find("translation").text or "").strip() or len(m.find("translation")))]
    assert unfinished == []


def test_every_qml_string_is_in_the_catalogue():
    catalogue = {m.find("source").text for m in ET.parse(TS).getroot().iter("message")}
    pattern = re.compile(r'qsTr\("((?:[^"\\]|\\.)*)"')
    missing = set()
    for qml in (ROOT / "chattoon" / "gui" / "qml").rglob("*.qml"):
        for text in pattern.findall(qml.read_text(encoding="utf-8")):
            text = text.encode().decode("unicode_escape").encode("latin-1").decode("utf-8")
            if text not in catalogue:
                missing.add(text)
    assert missing == set(), "run: python tools/update_translations.py"


def test_compiled_catalogue_is_up_to_date():
    qm = TS.with_suffix(".qm")
    assert qm.exists() and qm.stat().st_mtime >= TS.stat().st_mtime - 1


def test_translator_loads(qapp=None):
    from PySide6.QtCore import QCoreApplication, QTranslator

    app = QCoreApplication.instance() or QCoreApplication([])
    assert app is not None  # a Qt application must exist for QTranslator
    t = QTranslator()
    assert t.load(str(TS.with_suffix(".qm")))
    assert t.translate("Main", "Dashboard") == "Painel"
    assert t.translate("VoicePage", "%n voice(s) available", "", 3) == "%n vozes disponíveis"  # plural form
    assert t.translate("VoicePage", "%n voice(s) available", "", 1) == "%n voz disponível"
