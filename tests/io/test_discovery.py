import pytest

from termflex.io.io import FORMAT_SUFFIXES, collect_files, format_of, process_many
from corpus import LAYOUTS, write_corpus
from tests.io.fake_checkers import make_fake_checker

ALL = ["po", "xliff", "csv", "json"]


def _touch(p):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x", encoding="utf-8")
    return p


def test_recursive_walk_finds_only_supported_suffixes(tmp_path):
    wanted = [
        _touch(tmp_path / "af" / "LC_MESSAGES" / "django.po"),
        _touch(tmp_path / "uk" / "LC_MESSAGES" / "django.po"),
        _touch(tmp_path / "a.csv"), _touch(tmp_path / "b.json"),
        _touch(tmp_path / "c.xlf"), _touch(tmp_path / "d.xliff"),
        _touch(tmp_path / "UPPER.PO"),                    # suffix match is case-insensitive
    ]
    for ignored in ("af/LC_MESSAGES/django.mo", "README.md", "notes.txt", "x.pot"):
        _touch(tmp_path / ignored)

    assert collect_files(tmp_path, ALL) == sorted(wanted)


def test_directories_named_like_files_are_ignored(tmp_path):
    (tmp_path / "weird.po").mkdir()
    assert collect_files(tmp_path, ALL) == []


def test_single_file_path_returns_that_file(tmp_path):
    p = _touch(tmp_path / "a.po")
    assert collect_files(p) == [p]


def test_empty_directory(tmp_path):
    assert collect_files(tmp_path, ALL) == []
    assert process_many(tmp_path, make_fake_checker, max_workers=1, formats=ALL) == ([], {})


def test_single_unsupported_file_is_reported_as_error_not_crash(tmp_path):
    # collect_files returns a single file regardless of suffix; the loader then rejects it
    p = _touch(tmp_path / "notes.txt")
    results, errors = process_many(p, make_fake_checker, max_workers=1)
    assert results == [] and "unsupported file format" in errors[str(p)]


@pytest.mark.parametrize("layout", sorted(LAYOUTS))
def test_discovery_does_not_depend_on_directory_layout(tmp_path, layout):
    written = write_corpus(tmp_path, n_files=8, units_per_file=2, layout=layout)
    assert collect_files(tmp_path, ALL) == sorted(written)


@pytest.mark.parametrize("relpath", [
    "fr.po",                                   # flat, named after the language
    "messages.fr.po",                          # language as a middle segment
    "fr/django.po",                            # no LC_MESSAGES
    "locales/fr/LC_MESSAGES/django.po",
    "i18n/fr_CA/app/ui/strings.xlf",
    "very/deep/1/2/3/4/5/6/7/8/9/fr.po",
])
def test_various_conventions(tmp_path, relpath):
    p = _touch(tmp_path / relpath)
    assert collect_files(tmp_path, ALL) == [p]


# ---------- explicit formats ----------

def test_directory_without_formats_is_an_error(tmp_path):
    _touch(tmp_path / "a.po")
    with pytest.raises(ValueError, match="say which formats"):
        collect_files(tmp_path)
    with pytest.raises(ValueError, match="say which formats"):
        collect_files(tmp_path, [])


def test_unknown_format_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="unknown format"):
        collect_files(tmp_path, ["tmx"])


def test_missing_path_is_an_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        collect_files(tmp_path / "nope", ["po"])


def test_only_requested_formats_are_collected(tmp_path):
    po = _touch(tmp_path / "ok" / "a.po")
    xlf = _touch(tmp_path / "ok" / "a.xlf")         # same project folder, untranslated copy
    _touch(tmp_path / "data.json"); _touch(tmp_path / "pairs.csv")

    assert collect_files(tmp_path, ["po"]) == [po]
    assert collect_files(tmp_path, ["xliff"]) == [xlf]
    assert collect_files(tmp_path, ["po", "xliff"]) == sorted([po, xlf])
    assert [p.suffix for p in collect_files(tmp_path, ["json"])] == [".json"]


def test_xliff_covers_both_suffixes(tmp_path):
    a, b = _touch(tmp_path / "a.xlf"), _touch(tmp_path / "b.xliff")
    assert collect_files(tmp_path, ["xliff"]) == [a, b]


def test_format_of():
    assert [format_of(x) for x in ("a.PO", "a.xlf", "a.XLIFF", "a.csv", "a.json", "a.mo", "a")] == [
        "po", "xliff", "xliff", "csv", "json", None, None]
    assert set(FORMAT_SUFFIXES) == {"po", "xliff", "csv", "json"}
