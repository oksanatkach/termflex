import json

import pytest

from termflex import cli
from .corpus import write_corpus
from tests.io.fake_checkers import FakeChecker

COLS = ["--source-field", "en", "--target-field", "fr"]


@pytest.fixture(autouse=True)
def fake_checker(monkeypatch):
    # --workers 1 keeps everything in-process, so the monkeypatched factory is never pickled
    monkeypatch.setattr(cli, "make_checker", lambda tbx, src, tgt: FakeChecker())


def run(*args):
    return cli.main([*args, "--tbx", "g.tbx", "--src", "en", "--tgt", "fr", "--workers", "1"])


def usage_error(capsys, *args):
    with pytest.raises(SystemExit) as e:
        run(*args)
    assert e.value.code == 2
    return capsys.readouterr().err


def test_directory_without_format_is_a_usage_error(tmp_path, capsys):
    write_corpus(tmp_path, 4, 3)
    err = usage_error(capsys, str(tmp_path))
    assert "--format" in err and "directory" in err


def test_missing_input(tmp_path, capsys):
    assert "input not found" in usage_error(capsys, str(tmp_path / "nope"), "--format", "po")


def test_directory_with_no_files_of_the_requested_format(tmp_path, capsys):
    write_corpus(tmp_path, 3, 3)                              # po, csv, json - no xliff
    assert "no xliff files found" in usage_error(capsys, str(tmp_path), "--format", "xliff")


def test_csv_or_json_format_needs_field_names(tmp_path, capsys):
    write_corpus(tmp_path, 4, 3)
    assert "--source-field" in usage_error(capsys, str(tmp_path), "--format", "csv")


def test_po_only_run_does_not_need_field_names(tmp_path):
    write_corpus(tmp_path, 4, 3)
    assert run(str(tmp_path), "--format", "po") == 1          # failures found


def test_format_filter_limits_the_files_checked(tmp_path):
    write_corpus(tmp_path, 8, 3)
    out = tmp_path.parent / "out.json"
    run(str(tmp_path), "--format", "po", "--format", "json", *COLS, "--json", str(out))
    files = {r["file"] for r in json.loads(out.read_text(encoding="utf-8"))}
    assert files and all(f.endswith((".po", ".json")) for f in files)
    assert any(f.endswith(".po") for f in files) and any(f.endswith(".json") for f in files)


def test_single_file_infers_its_format(tmp_path):
    f = tmp_path / "a.csv"
    f.write_text("en,fr\nSend e-mail,Envoyer\n", encoding="utf-8")
    assert run(str(f), *COLS) == 1                            # no --format needed


def test_unsupported_single_file(tmp_path, capsys):
    f = tmp_path / "notes.txt"
    f.write_text("x", encoding="utf-8")
    assert "unsupported file type" in usage_error(capsys, str(f))


def test_format_flag_must_match_a_single_file(tmp_path, capsys):
    f = tmp_path / "a.csv"
    f.write_text("en,fr\na,b\n", encoding="utf-8")
    assert "is a csv file" in usage_error(capsys, str(f), "--format", "json", *COLS)


def test_exit_codes(tmp_path):
    clean = tmp_path / "clean.csv"
    clean.write_text("en,fr\nSend e-mail,Envoyer le courriel\n", encoding="utf-8")
    assert run(str(clean), *COLS) == 0                        # nothing wrong

    bad = tmp_path / "bad.csv"
    bad.write_text("en,fr\nSend e-mail,Envoyer\n", encoding="utf-8")
    assert run(str(bad), *COLS) == 1                          # term issues

    wrong = tmp_path / "wrong.csv"
    wrong.write_text("term,translation\na,b\n", encoding="utf-8")
    assert run(str(wrong), *COLS) == 2                        # file could not be read
