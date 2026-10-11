import json

import pytest

from termflex import cli
from .fake_checkers import FakeChecker

SCHEMA = {"root": "data.items", "pairs": {"source": "s", "target": "t"}}


calls: list = []


def _recorder(name):
    def load(path, **kwargs):
        calls.append((name, {"path": path, **kwargs}))
        return object()
    return load


@pytest.fixture(autouse=True)
def recording(monkeypatch, clean_registry):
    calls.clear()
    monkeypatch.setattr(cli, "GLOSSARY_LOADERS", {f".{n}": _recorder(n) for n in ("tbx", "po", "csv", "json")})
    monkeypatch.setattr(cli, "Checker", lambda glossary=None: FakeChecker())


@pytest.fixture
def work(tmp_path):
    """A directory with an input file and glossary files of every kind."""
    (tmp_path / "in.csv").write_text("en,fr\nSend e-mail,Envoyer\n", encoding="utf-8")
    (tmp_path / "g.tbx").write_text("<martif/>", encoding="utf-8")
    (tmp_path / "g.po").write_text('msgid ""\nmsgstr ""\n', encoding="utf-8")
    (tmp_path / "g.csv").write_text("en,fr\ne-mail,courriel\n", encoding="utf-8")
    (tmp_path / "g.json").write_text("{}", encoding="utf-8")
    (tmp_path / "g.dat").write_text("x", encoding="utf-8")
    (tmp_path / "schema.json").write_text(json.dumps(SCHEMA), encoding="utf-8")
    return tmp_path


def run(work, *glossary_args):
    return cli.main([str(work / "in.csv"), "--src", "en", "--tgt", "fr", "--workers", "1",
                     "--source-field", "en", "--target-field", "fr", *glossary_args])


def usage_error(capsys, work, *glossary_args):
    with pytest.raises(SystemExit) as e:
        run(work, *glossary_args)
    assert e.value.code == 2
    return capsys.readouterr().err


def test_tbx_is_inferred_from_the_extension(work):
    run(work, "--glossary", str(work / "g.tbx"))
    (name, kw), = calls
    assert name == "tbx" and kw["path"] == str(work / "g.tbx")
    assert kw["source_lang"] == "en" and kw["target_lang"] == "fr"


def test_tbx_flag_is_still_accepted(work):
    run(work, "--tbx", str(work / "g.tbx"))
    assert calls[0][0] == "tbx"


def test_po_glossary(work):
    run(work, "--glossary", str(work / "g.po"))
    assert calls[0][0] == "po"


def test_csv_glossary_passes_its_columns(work):
    run(work, "--glossary", str(work / "g.csv"),
        "--glossary-source-field", "en", "--glossary-target-field", "fr")
    (name, kw), = calls
    assert name == "csv"
    assert kw["source_term_column"] == "en" and kw["target_term_column"] == "fr"
    assert kw["path"] == str(work / "g.csv")


def test_json_glossary_passes_the_loaded_schema(work):
    run(work, "--glossary", str(work / "g.json"), "--glossary-schema", str(work / "schema.json"))
    (name, kw), = calls
    assert name == "json" and kw["schema"] == SCHEMA and kw["path"] == str(work / "g.json")


def test_explicit_format_overrides_the_extension(work):
    run(work, "--glossary", str(work / "g.dat"), "--glossary-format", "tbx")
    assert calls[0][0] == "tbx"


def test_unknown_extension_needs_an_explicit_format(work, capsys):
    err = usage_error(capsys, work, "--glossary", str(work / "g.dat"))
    assert "--glossary-format" in err
    assert not calls


def test_missing_glossary_file(work, capsys):
    assert "glossary not found" in usage_error(capsys, work, "--glossary", str(work / "nope.tbx"))


def test_csv_glossary_requires_both_columns(work, capsys):
    err = usage_error(capsys, work, "--glossary", str(work / "g.csv"), "--glossary-source-field", "en")
    assert "--glossary-source-field" in err and "--glossary-target-field" in err


def test_json_glossary_requires_a_schema(work, capsys):
    assert "--glossary-schema" in usage_error(capsys, work, "--glossary", str(work / "g.json"))


def test_bad_schema_file_is_reported(work, capsys):
    (work / "bad.json").write_text("{not json", encoding="utf-8")
    err = usage_error(capsys, work, "--glossary", str(work / "g.json"),
                      "--glossary-schema", str(work / "bad.json"))
    assert "--glossary-schema" in err


def test_lemmatizer_flags_reach_every_loader(work):
    run(work, "--glossary", str(work / "g.po"), "--lemmatizer", "simplemma")
    assert calls[0][1]["source_lemmatizer"] == "simplemma"


def test_glossary_spec_pickles_for_worker_processes():
    import pickle
    spec = cli.GlossarySpec("g.json", ".json", {"schema": SCHEMA})
    assert pickle.loads(pickle.dumps(spec)) == spec
