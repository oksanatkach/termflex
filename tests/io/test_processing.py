import pytest

from termflex.io.io import check_file, load_units, process_many
from corpus import FIELD_OPTIONS, LAYOUTS, expected_failures, write_corpus
from tests.io.fake_checkers import FakeChecker, make_fake_checker

ALL = ["po", "xliff", "csv", "json"]


def test_load_units_dispatch_errors(tmp_path):
    csv_p = tmp_path / "a.csv"
    csv_p.write_text("en,fr\na,b\n", encoding="utf-8")
    with pytest.raises(ValueError, match="source_col"):
        load_units(csv_p, None)
    with pytest.raises(ValueError, match="unsupported"):
        load_units(tmp_path / "a.txt")


def test_check_file_keeps_only_failures_and_skips_empty_targets(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text("en,fr\n"
                 "Send e-mail,Envoyer le courriel\n"   # ok
                 "Send e-mail,Envoyer le message\n"    # fail
                 "Send e-mail,\n"                      # untranslated -> skipped
                 "Hello,Bonjour\n",                    # no glossary term -> nothing to report
                 encoding="utf-8")
    results = check_file(p, FakeChecker(), FIELD_OPTIONS)
    assert [r["line"] for r in results] == [3]
    assert results[0]["issues"] == [{"term": "e-mail", "expected": ["courriel"]}]
    assert set(results[0]) == {"file", "line", "plural_index", "context", "source", "target", "issues"}


def test_results_match_the_known_failure_count(tmp_path):
    write_corpus(tmp_path, n_files=8, units_per_file=9)       # 2 files per format
    results, errors = process_many(tmp_path, make_fake_checker, FIELD_OPTIONS, max_workers=1, formats=ALL)
    assert errors == {}
    assert sum(len(r["issues"]) for r in results) == 8 * expected_failures(9)
    assert len({r["file"] for r in results}) == 8


def test_parallel_results_equal_sequential_results(tmp_path):
    write_corpus(tmp_path, n_files=16, units_per_file=12)
    seq, e1 = process_many(tmp_path, make_fake_checker, FIELD_OPTIONS, max_workers=1, formats=ALL)
    par, e2 = process_many(tmp_path, make_fake_checker, FIELD_OPTIONS, max_workers=3, formats=ALL)
    assert e1 == e2 == {}
    assert seq == par                                         # same content AND same order
    assert [(r["file"], r["line"]) for r in par] == sorted((r["file"], r["line"]) for r in par)


def test_one_broken_file_does_not_kill_the_run(tmp_path):
    write_corpus(tmp_path, n_files=8, units_per_file=6)
    broken = tmp_path / "lang0" / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    wrong_cols = tmp_path / "lang1" / "glossary.csv"
    wrong_cols.write_text("term,translation\na,b\n", encoding="utf-8")

    for workers in (1, 2):
        results, errors = process_many(tmp_path, make_fake_checker, FIELD_OPTIONS, max_workers=workers, formats=ALL)
        assert set(errors) == {str(broken), str(wrong_cols)}
        assert "JSONDecodeError" in errors[str(broken)]
        assert "not found" in errors[str(wrong_cols)]
        assert sum(len(r["issues"]) for r in results) == 8 * expected_failures(6)


def test_csv_without_field_options_is_an_error_per_file(tmp_path):
    write_corpus(tmp_path, n_files=4, units_per_file=3)       # one csv among them
    results, errors = process_many(tmp_path, make_fake_checker, None, max_workers=1, formats=ALL)
    assert len(errors) == 2                                   # the csv and the json
    assert all("field_options" in e for e in errors.values())
    assert results                                            # po / xlf still processed


@pytest.mark.parametrize("layout", sorted(LAYOUTS))
def test_end_to_end_on_any_layout(tmp_path, layout):
    write_corpus(tmp_path, n_files=8, units_per_file=6, layout=layout)
    results, errors = process_many(tmp_path, make_fake_checker, FIELD_OPTIONS, max_workers=2, formats=ALL)
    assert errors == {}
    assert sum(len(r["issues"]) for r in results) == 8 * expected_failures(6)


def test_format_selection_limits_what_is_processed(tmp_path):
    write_corpus(tmp_path, n_files=8, units_per_file=6)       # 2 files per format
    results, errors = process_many(tmp_path, make_fake_checker, FIELD_OPTIONS,
                                   max_workers=1, formats=["po"])
    assert errors == {}
    assert {r["file"][-3:] for r in results} == {".po"}
    assert sum(len(r["issues"]) for r in results) == 2 * expected_failures(6)
