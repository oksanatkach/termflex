import pytest

from termflex import cli
from .fake_checkers import FakeChecker


pytestmark = pytest.mark.usefixtures("glossary_cwd")


class RecordingGlossary:
    calls: list = []

    @classmethod
    def from_tbx(cls, path, **kwargs):
        cls.calls.append(kwargs)
        return object()


@pytest.fixture(autouse=True)
def recording(monkeypatch, clean_registry):
    RecordingGlossary.calls = []
    monkeypatch.setattr(cli, "GLOSSARY_LOADERS", {".tbx": RecordingGlossary.from_tbx})
    monkeypatch.setattr(cli, "Checker", lambda glossary=None: FakeChecker())


@pytest.fixture
def csv_file(tmp_path):
    f = tmp_path / "a.csv"
    f.write_text("en,fr\nSend e-mail,Envoyer\n", encoding="utf-8")
    return str(f)


def run(path, *extra):
    return cli.main([path, "--tbx", "g.tbx", "--src", "en", "--tgt", "fr", "--workers", "1",
                     "--source-field", "en", "--target-field", "fr", *extra])


def usage_error(capsys, *args):
    with pytest.raises(SystemExit) as e:
        run(*args)
    assert e.value.code == 2
    return capsys.readouterr().err


def test_no_flags_passes_no_lemmatizer_arguments(csv_file):
    assert run(csv_file) == 1
    (kwargs,) = RecordingGlossary.calls
    assert "source_lemmatizer" not in kwargs and "target_lemmatizer" not in kwargs


def test_lemmatizer_flag_applies_to_both_sides(csv_file):
    run(csv_file, "--lemmatizer", "pymorphy3")
    (kwargs,) = RecordingGlossary.calls
    assert kwargs["source_lemmatizer"] == kwargs["target_lemmatizer"] == "pymorphy3"


def test_auto_is_passed_through(csv_file):
    run(csv_file, "--lemmatizer", "auto")
    assert RecordingGlossary.calls[0]["source_lemmatizer"] == "auto"


def test_per_side_flags_override_the_shared_one(csv_file):
    run(csv_file, "--lemmatizer", "simplemma", "--target-lemmatizer", "pymorphy3")
    (kwargs,) = RecordingGlossary.calls
    assert (kwargs["source_lemmatizer"], kwargs["target_lemmatizer"]) == ("simplemma", "pymorphy3")


def test_only_one_side_given(csv_file):
    run(csv_file, "--source-lemmatizer", "pymorphy3")
    (kwargs,) = RecordingGlossary.calls
    assert kwargs == {"source_lang": "en", "target_lang": "fr",
                      "source_lemmatizer": "pymorphy3"}


def test_module_path_function_is_resolved_and_passed_as_a_callable(tmp_path, csv_file, monkeypatch):
    (tmp_path / "my_lemmas.py").write_text("def lem(text, lang_code):\n    return text.split()\n", encoding="utf-8")
    (tmp_path / "g.tbx").write_text("<martif/>", encoding="utf-8")   # chdir hides the fixture's glossary
    monkeypatch.chdir(tmp_path)
    run(csv_file, "--source-lemmatizer", "my_lemmas:lem")
    fn = RecordingGlossary.calls[0]["source_lemmatizer"]
    assert callable(fn) and fn("a b", "en") == ["a", "b"]


def test_module_path_backend_class_is_registered_and_passed_by_name(tmp_path, csv_file, monkeypatch, clean_registry):
    (tmp_path / "my_cls.py").write_text(
        "from termflex.lemmatizers.morph_backends import Backend\n"
        "class Mine(Backend):\n    name = 'mine-cli'\n    def _lemmatize(self, t): return t.split()\n", encoding="utf-8")
    (tmp_path / "g.tbx").write_text("<martif/>", encoding="utf-8")   # chdir hides the fixture's glossary
    monkeypatch.chdir(tmp_path)
    run(csv_file, "--lemmatizer", "my_cls:Mine")
    kwargs = RecordingGlossary.calls[0]
    assert kwargs["source_lemmatizer"] == kwargs["target_lemmatizer"] == "mine-cli"
    assert "mine-cli" in clean_registry._REGISTRY


@pytest.mark.parametrize("flag", ["--lemmatizer", "--source-lemmatizer", "--target-lemmatizer"])
def test_unknown_backend_is_a_usage_error_naming_the_flag(flag, csv_file, capsys, monkeypatch):
    # must fail before any worker is started
    monkeypatch.setattr(cli, "process_many", lambda *a, **k: pytest.fail("processing started"))
    err = usage_error(capsys, csv_file, flag, "nope")
    assert flag in err and "Unknown backend 'nope'" in err


def test_broken_module_path_is_a_usage_error(csv_file, capsys, monkeypatch):
    monkeypatch.setattr(cli, "process_many", lambda *a, **k: pytest.fail("processing started"))
    assert "Cannot import module" in usage_error(capsys, csv_file, "--lemmatizer", "no_such_mod_xyz:thing")


def test_list_backends_needs_no_other_arguments(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["--list-backends"])
    assert e.value.code == 0
    out = capsys.readouterr().out
    assert "pymorphy3: ru, uk" in out and "simplemma:" in out and "auto:" in out
