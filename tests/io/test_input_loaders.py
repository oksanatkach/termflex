import json

import polib
import pytest

from termflex.io.input_loaders.csv_input_parser import load_csv_units
from termflex.io.input_loaders.json_input_parser import load_json_units
from termflex.io.input_loaders.po_input_parser import load_po_units
from termflex.io.input_loaders.xliff_input_parser import load_xliff_units

KEYS = ["source", "target", "context", "plural_index", "lineno"]


# ---------- PO ----------

def _po(tmp_path, entries):
    po = polib.POFile()
    po.metadata = {"Content-Type": "text/plain; charset=UTF-8"}
    for e in entries:
        po.append(e)
    p = tmp_path / "a.po"
    po.save(str(p))
    return p


def test_po_plural_forms_pair_with_the_right_source(tmp_path):
    p = _po(tmp_path, [polib.POEntry(
        msgid="%d file", msgid_plural="%d files",
        msgstr_plural={0: "%d fichier", 1: "%d fichiers", 2: "%d fichiers (many)"})])
    units = list(load_po_units(p))
    assert [(u["plural_index"], u["source"]) for u in units] == [
        (0, "%d file"), (1, "%d files"), (2, "%d files")]


def test_po_single_form_language_gets_both_sources(tmp_path):
    p = _po(tmp_path, [polib.POEntry(
        msgid="%d file", msgid_plural="%d files", msgstr_plural={0: "%d ファイル"})])
    (u,) = load_po_units(p)
    assert u["source"] == "%d file\n%d files"


def test_po_skips_obsolete_and_fuzzy(tmp_path):
    p = _po(tmp_path, [
        polib.POEntry(msgid="keep", msgstr="garde"),
        polib.POEntry(msgid="old", msgstr="vieux", obsolete=True),
        polib.POEntry(msgid="guess", msgstr="devinette", flags=["fuzzy"]),
    ])
    assert [u["source"] for u in load_po_units(p)] == ["keep"]
    assert len(list(load_po_units(p, skip_fuzzy=False))) == 2


def test_po_context_and_keys(tmp_path):
    p = _po(tmp_path, [polib.POEntry(msgid="Open", msgstr="Ouvrir", msgctxt="menu")])
    (u,) = load_po_units(p)
    assert list(u) == KEYS and u["context"] == "menu" and u["plural_index"] is None


# ---------- CSV ----------

def test_csv_semicolon_delimiter_and_bom(tmp_path):
    p = tmp_path / "a.csv"
    p.write_bytes("\ufeffEnglish;French\nHello;Bonjour\n".encode("utf-8"))
    (u,) = load_csv_units(p, source_col="English", target_col="French")
    assert (u["source"], u["target"], u["lineno"]) == ("Hello", "Bonjour", 2)


def test_csv_missing_column_lists_available(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text("en,fr\nHi,Salut\n", encoding="utf-8")
    with pytest.raises(ValueError, match="available columns"):
        list(load_csv_units(p, source_col="English", target_col="fr"))


def test_csv_empty_cells_and_context(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text("en,fr,ctx\nHi,,\nBye,Au revoir,menu\n", encoding="utf-8")
    a, b = load_csv_units(p, "en", "fr", context_col="ctx")
    assert a["target"] == "" and a["context"] is None and b["context"] == "menu"


def test_csv_quoted_multiline_field(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text('en,fr\n"line1\nline2",ligne\n', encoding="utf-8")
    (u,) = load_csv_units(p, "en", "fr")
    assert u["source"] == "line1\nline2"


# ---------- JSON ----------

def test_json_basic_null_and_context(tmp_path):
    p = tmp_path / "a.json"
    p.write_text(json.dumps([{"en": "Hi", "fr": "Salut", "c": "x"}, {"en": "Bye", "fr": None}]),
                 encoding="utf-8")
    a, b = load_json_units(p, "en", "fr", context_col="c")
    assert (a["lineno"], a["context"], b["target"], b["context"]) == (1, "x", "", None)


def test_json_errors(tmp_path):
    p = tmp_path / "a.json"
    p.write_text('{"not": "a list"}', encoding="utf-8")
    with pytest.raises(ValueError, match="list"):
        list(load_json_units(p, "en", "fr"))

    p.write_text('[{"en": "Hi", "fr": 5}]', encoding="utf-8")
    with pytest.raises(ValueError, match="must be a string"):
        list(load_json_units(p, "en", "fr"))

    p.write_text('[{"en": "Hi", "fr": "x"}]', encoding="utf-8")
    with pytest.raises(ValueError, match="available keys"):
        list(load_json_units(p, "english", "fr"))


# ---------- XLIFF ----------

XLF12 = """<?xml version="1.0" encoding="UTF-8"?>
<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2"><file original="a"><body>
<trans-unit id="1" resname="mail.send">
  <source>Send it to my <g id="1">e-mail</g><x id="2"/> now<ph id="3">%s</ph></source>
  <target>Envoyez à mon <g id="1">courriel</g><x id="2"/> maintenant</target></trans-unit>
<trans-unit id="2" translate="no"><source>Brand</source><target>Brand</target></trans-unit>
<trans-unit id="3"><source>Untranslated</source></trans-unit>
</body></file></xliff>"""

XLF20 = """<?xml version="1.0" encoding="UTF-8"?>
<xliff version="2.0" xmlns="urn:oasis:names:tc:xliff:document:2.0" srcLang="en" trgLang="fr">
<file id="f1"><unit id="u1" name="greeting">
  <segment><source>Hello <pc id="1">world</pc></source><target>Bonjour <pc id="1">monde</pc></target></segment>
  <ignorable><source> </source></ignorable>
  <segment><source>Bye</source><target>Au revoir</target></segment>
</unit></file></xliff>"""


def test_xliff_12(tmp_path):
    p = tmp_path / "a.xlf"
    p.write_text(XLF12, encoding="utf-8")
    a, b = load_xliff_units(p)  # translate="no" unit is skipped
    assert a["source"] == "Send it to my e-mail now"        # <ph> code content dropped
    assert a["target"] == "Envoyez à mon courriel maintenant"
    assert a["context"] == "mail.send"
    assert b["source"] == "Untranslated" and b["target"] == ""


def test_xliff_20(tmp_path):
    p = tmp_path / "a.xlf"
    p.write_text(XLF20, encoding="utf-8")
    a, b = load_xliff_units(p)  # <ignorable> is skipped
    assert (a["source"], a["target"], a["context"]) == ("Hello world", "Bonjour monde", "greeting")
    assert b["source"] == "Bye"


# ---------- the contract every loader must honour ----------

def test_all_loaders_yield_identical_keys(tmp_path):
    po = _po(tmp_path, [polib.POEntry(msgid="a", msgstr="b")])
    csv_p = tmp_path / "a.csv"; csv_p.write_text("en,fr\na,b\n", encoding="utf-8")
    json_p = tmp_path / "a.json"; json_p.write_text('[{"en":"a","fr":"b"}]', encoding="utf-8")
    xlf = tmp_path / "a.xlf"; xlf.write_text(XLF20, encoding="utf-8")

    units = [
        next(load_po_units(po)),
        next(load_csv_units(csv_p, "en", "fr")),
        next(load_json_units(json_p, "en", "fr")),
        next(load_xliff_units(xlf)),
    ]
    for u in units:
        assert list(u) == KEYS
        assert isinstance(u["source"], str) and isinstance(u["target"], str)
        assert isinstance(u["lineno"], int)
