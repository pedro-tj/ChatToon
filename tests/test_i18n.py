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
    from PySide6.QtCore import QTranslator
    from PySide6.QtWidgets import QApplication

    # a QApplication (not a bare QCoreApplication): GUI tests running after this one reuse it
    app = QApplication.instance() or QApplication([])
    assert app is not None  # a Qt application must exist for QTranslator
    t = QTranslator()
    assert t.load(str(TS.with_suffix(".qm")))
    assert t.translate("Main", "Dashboard") == "Painel"
    assert t.translate("VoicePage", "%n voice(s) available", "", 3) == "%n vozes disponíveis"  # plural form
    assert t.translate("VoicePage", "%n voice(s) available", "", 1) == "%n voz disponível"


def test_translations_keep_every_placeholder():
    """A translation that drops or invents %1/%2/%n shows garbage (or the wrong number) on screen."""
    marks = re.compile(r"%(?:\d|n)")
    broken = []
    for m in ET.parse(TS).getroot().iter("message"):
        source = m.find("source").text or ""
        tr = m.find("translation")
        forms = [f.text or "" for f in tr.findall("numerusform")] or [tr.text or ""]
        want = sorted(marks.findall(source))
        for form in forms:
            got = sorted(marks.findall(form))
            # a singular plural form may spell the number out ("1 voz" written as "uma voz")
            if got != want and not (m.get("numerus") == "yes" and set(got) <= set(want)):
                broken.append(f"{source!r} -> {form!r}")
    assert broken == []


def test_python_interface_strings_are_translatable():
    """Strings shown by the GUI's Python controllers go through self.tr(), never raw literals."""
    gui = ROOT / "chattoon" / "gui"
    offenders = []
    for py in gui.glob("*.py"):
        for i, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"notify\(\s*\"[A-Z]", line) or re.search(r"toast\.emit\(\s*\"[A-Z]", line):
                offenders.append(f"{py.name}:{i}")
    assert offenders == []


def test_interface_language_choice(monkeypatch):
    from PySide6.QtCore import QCoreApplication, QLocale
    from PySide6.QtWidgets import QApplication

    from chattoon.gui.app import install_translator

    app = QApplication.instance() or QApplication([])
    pt = install_translator(app, "pt_BR")
    assert pt is not None and QCoreApplication.translate("Main", "Dashboard") == "Painel"
    app.removeTranslator(pt)
    assert install_translator(app, "en") is None  # English is the source language: no catalogue
    assert QCoreApplication.translate("Main", "Dashboard") == "Dashboard"
    monkeypatch.setattr(QLocale, "system", staticmethod(lambda: QLocale("pt_BR")))
    auto = install_translator(app, "system")  # follows the desktop's language
    assert auto is not None
    app.removeTranslator(auto)
