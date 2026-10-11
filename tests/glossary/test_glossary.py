"""Unit tests for Glossary construction: the from_* loaders and _build."""
from __future__ import annotations
import json
import pytest

from termflex import Glossary
from termflex.lemmatizers import UnsupportedLanguageError
from termflex.utils.lang import InvalidLanguageError

from tests import en_lem, uk_lem, MULTI, PAIRS, SCHEMA, GLOSSARY_JSON

TOY = {"source_lemmatizer": en_lem, "target_lemmatizer": uk_lem}


# =========================
# Glossary files
# =========================


def write_json(path, pairs, encoding="utf-8"):
    glossary_json = {"terms": [{"en": s, "uk": t} for s, t in pairs]}
    with open(path, "w", encoding=encoding) as f:
        json.dump(glossary_json, f, indent=2, ensure_ascii=False)
    return path


def write_csv(path, pairs, delimiter=",", encoding="utf-8"):
    rows = [("en", "uk"), *pairs]
    path.write_text("".join(f"{s}{delimiter}{t}\n" for s, t in rows), encoding=encoding)
    return path


def write_tbx(path, pairs):
    grouped: dict[str, list[str]] = {}
    for s, t in pairs:
        grouped.setdefault(s, []).append(t)
    entries = []
    for i, (s, targets) in enumerate(grouped.items()):
        tigs = "".join(f"<tig><term>{t}</term></tig>" for t in targets)
        entries.append(
            f'<termEntry id="t{i}">'
            f'<langSet xml:lang="en"><tig><term>{s}</term></tig></langSet>'
            f'<langSet xml:lang="uk">{tigs}</langSet>'
            f"</termEntry>"
        )
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<martif type="TBX" xml:lang="en"><text><body>'
        + "".join(entries)
        + "</body></text></martif>\n",
        encoding="utf-8",
    )
    return path


def write_po(path, pairs):
    header = 'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n'
    entries = "".join(f'\nmsgid "{s}"\nmsgstr "{t}"\n' for s, t in pairs)
    path.write_text(header + entries, encoding="utf-8")
    return path

# =========================
# Loaders: same terms, any format
# =========================

def test_all_formats_load_the_same_terms(tmp_path):
    glossary_csv = Glossary.from_csv(write_csv(tmp_path / "g.csv", PAIRS), "en", "uk", "en", "uk", **TOY)
    glossary_json_file = Glossary.from_json(write_json(tmp_path / "g.json", PAIRS), "en", "uk", schema=SCHEMA, **TOY)
    glossary_json_obj = Glossary.from_json(GLOSSARY_JSON, "en", "uk", schema=SCHEMA, **TOY)
    glossary_tbx = Glossary.from_tbx(write_tbx(tmp_path / "g.tbx", PAIRS), "en", "uk", **TOY)
    glossary_po = Glossary.from_po(write_po(tmp_path / "g.po", PAIRS), "en", "uk", **TOY)
    for glossary in [glossary_json_file, glossary_json_obj, glossary_tbx, glossary_po]:
        assert glossary.target_map == glossary_csv.target_map


def test_multiple_targets_per_source(tmp_path):
    single_glossary_csv = Glossary.from_csv(write_csv(tmp_path / "single.csv", PAIRS), "en", "uk", "en", "uk", **TOY)
    glossary_csv = Glossary.from_csv(write_csv(tmp_path / "g.csv", MULTI), "en", "uk", "en", "uk", **TOY)
    glossary_json_file = Glossary.from_json(write_json(tmp_path / "g.json", MULTI), "en", "uk", schema=SCHEMA, **TOY)
    glossary_json_obj = Glossary.from_json({"terms": [{"en": s, "uk": t} for s, t in MULTI]}, "en", "uk", schema=SCHEMA, **TOY)
    glossary_tbx = Glossary.from_tbx(write_tbx(tmp_path / "g.tbx", MULTI), "en", "uk", **TOY)
    glossary_po = Glossary.from_po(write_po(tmp_path / "g.po", MULTI), "en", "uk", **TOY)
    assert single_glossary_csv.target_map != glossary_csv.target_map
    for glossary in [glossary_json_file, glossary_json_obj, glossary_tbx, glossary_po]:
        assert glossary.target_map == glossary_csv.target_map


# =========================
# Loader options
# =========================


def test_csv_delimiter(tmp_path):
    default = Glossary.from_csv(write_csv(tmp_path / "a.csv", MULTI), "en", "uk", "en", "uk", **TOY)
    semicolon = Glossary.from_csv(
        write_csv(tmp_path / "b.csv", MULTI, delimiter=";"), "en", "uk", "en", "uk",
        delimiter=";", **TOY,
    )
    assert semicolon.target_map == default.target_map


def test_csv_encoding(tmp_path):
    utf8 = Glossary.from_csv(write_csv(tmp_path / "a.csv", MULTI), "en", "uk", "en", "uk", **TOY)
    cp1251 = Glossary.from_csv(
        write_csv(tmp_path / "b.csv", MULTI, encoding="cp1251"), "en", "uk", "en", "uk",
        encoding="cp1251", **TOY,
    )
    assert cp1251.target_map == utf8.target_map


def test_json_encoding(tmp_path):
    utf8 = Glossary.from_json(write_json(tmp_path / "a.json", MULTI), "en", "uk", schema=SCHEMA, **TOY)
    cp1251 = Glossary.from_json(
        write_json(tmp_path / "b.json", MULTI, encoding="cp1251"), "en", "uk",
        schema=SCHEMA, encoding="cp1251", **TOY,
    )
    assert cp1251.target_map == utf8.target_map


# =========================
# _build
# =========================


def test_attributes(tmp_path):
    g = Glossary.from_csv(write_csv(tmp_path / "g.csv", PAIRS), "en", "uk", "en", "uk", **TOY)
    assert g.source_lang.language == "en"
    assert g.target_lang.language == "uk"
    assert g.source_lemmatizer is en_lem
    assert g.target_lemmatizer is uk_lem


def test_empty_glossary_raises(tmp_path):
    with pytest.raises(ValueError, match="does not contain any terms"):
        Glossary.from_csv(write_csv(tmp_path / "g.csv", []), "en", "uk", "en", "uk", **TOY)


def test_invalid_language_raises(tmp_path):
    with pytest.raises(InvalidLanguageError):
        Glossary.from_csv(write_csv(tmp_path / "g.csv", PAIRS), "en", "uk", "not a language", "uk", **TOY)


def test_unknown_backend_raises(tmp_path):
    with pytest.raises(ValueError, match="Unknown backend"):
        Glossary.from_csv(
            write_csv(tmp_path / "g.csv", PAIRS), "en", "uk", "en", "uk", lemmatizer="no-such-backend",
        )


def test_backend_without_language_support_raises(tmp_path):
    with pytest.raises(UnsupportedLanguageError, match="Language is not supported"):
        Glossary.from_csv(
            write_csv(tmp_path / "g.csv", PAIRS), "en", "uk", "en", "uk",
            source_lemmatizer="pymorphy3", target_lemmatizer=uk_lem,
        )


def test_backend_instance_for_wrong_language_raises(tmp_path):
    with pytest.raises(UnsupportedLanguageError, match="Language is not supported"):
        Glossary.from_csv(
            write_csv(tmp_path / "g.csv", PAIRS), "en", "uk", "en", "uk",
            source_lemmatizer=en_lem, target_lemmatizer=en_lem,
        )


def test_per_side_lemmatizers_override_lemmatizer(tmp_path):
    g = Glossary.from_csv(
        write_csv(tmp_path / "g.csv", PAIRS), "en", "uk", "en", "uk",
        lemmatizer="no-such-backend", **TOY,
    )
    assert g.source_lemmatizer is en_lem
    assert g.target_lemmatizer is uk_lem


def test_auto_resolves_to_simplemma(tmp_path):
    pytest.importorskip("simplemma")
    g = Glossary.from_csv(write_csv(tmp_path / "g.csv", PAIRS), "en", "uk", "en", "uk", lemmatizer="auto")
    assert g.source_lemmatizer.name == "simplemma"
    assert g.target_lemmatizer.name == "simplemma"
