"""Unit tests for termflex.checker.

Real Glossary, Doc, OffsetMap and matching utils; only the lemmatizer is a toy
Backend, so expected lemmas are obvious and don't drift with library versions.
"""
from __future__ import annotations

import dataclasses

import pytest

import termflex.checker as checker_mod
from termflex import Glossary
from termflex.checker import (
    Checker,
    RenderedTermMatch,
    TermMatch,
    _lazy,
    wrap_lemmas,
    wrap_text,
)
from termflex.utils.doc import Doc
from termflex.utils.offsets import OffsetMap
from tests import GLOSSARY_JSON, SCHEMA, en_lem, uk_lem


@pytest.fixture(scope="module")
def checker():
    glossary = Glossary.from_json(
        GLOSSARY_JSON, "en", "uk", schema=SCHEMA, source_lemmatizer=en_lem, target_lemmatizer=uk_lem
    )
    return Checker(glossary)


# =========================
# wrap_lemmas
# =========================

@pytest.mark.parametrize(
    "first, last, expected",
    [
        (0, 0, "<term>a</term> b c"),
        (1, 1, "a <term>b</term> c"),
        (2, 2, "a b <term>c</term>"),
        (1, 2, "a <term>b c</term>"),
        (0, 2, "<term>a b c</term>"),
    ],
)
def test_wrap_lemmas(first, last, expected):
    assert wrap_lemmas(["a", "b", "c"], first, last) == expected


def test_wrap_lemmas_custom_tag():
    assert wrap_lemmas(["a", "b"], 0, 0, tag="x") == "<x>a</x> b"


def test_wrap_lemmas_does_not_mutate_input():
    lemmas = ["a", "b"]
    wrap_lemmas(lemmas, 0, 1)
    assert lemmas == ["a", "b"]


# =========================
# wrap_text
# =========================

@pytest.mark.parametrize(
    "span, expected",
    [
        ((0, 2), "<term>abc</term> def ghi"),
        ((4, 6), "abc <term>def</term> ghi"),
        ((8, 10), "abc def <term>ghi</term>"),
        ((4, 4), "abc <term>d</term>ef ghi"),
    ],
)
def test_wrap_text_inclusive_end(span, expected):
    text = "abc def ghi"
    assert wrap_text(text, span, OffsetMap.build(text, lambda s: s)) == expected


def test_wrap_text_custom_tag():
    text = "abc"
    assert wrap_text(text, (0, 2), OffsetMap.build(text, lambda s: s), tag="x") == "<x>abc</x>"


# =========================
# _lazy
# =========================

def test_lazy_defers_and_caches():
    calls = []
    get = _lazy(lambda: calls.append(1) or "value")
    assert calls == []
    assert get() == "value"
    assert get() == "value"
    assert calls == [1]


def test_lazy_caches_falsy_value():
    calls = []
    get = _lazy(lambda: calls.append(1))  # returns None
    get()
    get()
    assert calls == [1]


# =========================
# Checker: source side
# =========================

def test_no_source_terms_returns_empty(checker):
    assert checker.check("nothing to see here", "сервер") == []


def test_source_fields(checker):
    source = "restart the server now"
    [r] = checker.check(source, "перезапустіть сервер")
    assert r.source_term == "server"
    assert r.source_span == (12, 17)
    assert r.source_lemma_span == (2, 2)
    assert r.source_lemmas == Doc.from_text(source, en_lem).lemmas


def test_one_result_per_source_term_in_order(checker):
    results = checker.check("restart the server and the database", "перезапустіть сервер")
    assert [r.source_term for r in results] == ["server", "database"]
    assert [r.match for r in results] == [True, False]


def test_inflected_source_term_is_found(checker):
    [r] = checker.check("restart the servers", "перезапустіть сервер")
    assert r.source_term == "server"
    assert r.match


# =========================
# Checker: match classification
# =========================

@pytest.mark.parametrize(
    "source, target, expected",
    [
        ("restart the server", "перезапустіть сервер", "exact"),
        ("update the database", "оновіть бази даних", "lemma"),
        ("restart the server", "перезапустіть машину", "missing"),
    ],
)
def test_match_type(checker, source, target, expected):
    [r] = checker.check(source, target)
    assert r.match_type == expected
    assert r.match is (expected != "missing")


def test_exact_spans(checker):
    source_text = "restart the server"
    target_text = "будь ласка, перезапустіть сервер"
    [r] = checker.check(source_text, target_text)
    doc = Doc.from_text(target_text, uk_lem)
    assert r.target_lemma_span == (3, 3)
    assert r.target_span == doc.char_span(3, 3)
    assert r.target_lemmas == doc.lemmas
    assert r.found_targets == ["сервер"]
    assert r.expected_targets == ["сервер", "хост"]


def test_lemma_only_multi_token(checker):
    [r] = checker.check("update the database", "оновіть бази даних")
    assert r.match_type == "lemma"
    assert r.target_lemma_span == (1, 2)
    assert r.target_span is None
    assert r.found_targets == ["база даних"]


def test_missing(checker):
    [r] = checker.check("restart the server", "перезапустіть машину")
    assert r.match is False
    assert r.match_type == "missing"
    assert r.found_targets == []
    assert r.expected_targets == ["сервер", "хост"]
    assert r.target_span is None
    assert r.target_lemma_span is None
    assert r.target_lemmas is None


@pytest.mark.parametrize("text, token", [("сервер працює", 0), ("перезапустіть сервер", 1)])
def test_target_at_text_boundaries(checker, text, token):
    [r] = checker.check("restart the server", text)
    assert r.match_type == "exact"
    assert r.target_lemma_span == (token, token)
    assert r.target_span == Doc.from_text(text, uk_lem).char_span(token, token)


def test_empty_target_text(checker):
    [r] = checker.check("restart the server", "")
    assert r.match_type == "missing"


# =========================
# Checker: candidate selection
# =========================

def test_best_candidate_by_priority_not_order(checker):
    text = "оновіть бази даних або бд"  # "база даних" -> lemma, "бд" -> exact
    [r] = checker.check("update the database", text)
    assert r.match_type == "exact"
    assert r.target_lemma_span == (4, 4)
    assert r.target_span == Doc.from_text(text, uk_lem).char_span(4, 4)
    assert r.found_targets == ["база даних", "бд"]


def test_tie_goes_to_first_target(checker):
    [r] = checker.check("restart the server", "сервер або хост")
    assert r.match_type == "exact"
    assert r.target_lemma_span == (0, 0)
    assert r.found_targets == ["сервер", "хост"]


# =========================
# Checker: current behavior worth revisiting
# =========================

def test_documents_repeated_source_term_reuses_one_target_occurrence(checker):
    results = checker.check("restart the server then the server again", "перезапустіть сервер")
    assert len(results) == 2
    assert all(r.match for r in results)
    assert results[0].target_span == results[1].target_span


def test_documents_exact_does_not_require_coinciding_hits(checker):
    text = "бази даних і база даних"
    [r] = checker.check("update the database", text)
    assert r.match_type == "exact"
    assert r.target_lemma_span == (0, 1)  # "бази даних"
    assert r.target_span == Doc.from_text(text, uk_lem).char_span(3, 4)  # "база даних"


# =========================
# Checker: result shape
# =========================

CASES = [
    ("restart the server", "перезапустіть сервер"),
    ("update the database", "оновіть бази даних"),
    ("restart the server", "перезапустіть машину"),
]


@pytest.mark.parametrize("source, target", CASES)
def test_render_false_returns_plain_termmatch(checker, source, target):
    [r] = checker.check(source, target)
    assert type(r) is TermMatch


@pytest.mark.parametrize("source, target", CASES)
def test_rendered_base_fields_equal_unrendered(checker, source, target):
    [plain] = checker.check(source, target)
    [rendered] = checker.check(source, target, render=True)
    assert type(rendered) is RenderedTermMatch
    for f in dataclasses.fields(TermMatch):
        assert getattr(rendered, f.name) == getattr(plain, f.name), f.name


# =========================
# Checker: rendering
# =========================

def test_render_exact(checker):
    [r] = checker.check("Restart the server now", "Перезапустіть сервер зараз", render=True)
    assert r.source_rendered == "Restart the <term>server</term> now"
    assert r.target_rendered == "Перезапустіть <term>сервер</term> зараз"
    assert r.source_lemmas_rendered == "restart the <term>server</term> now"
    assert r.target_lemmas_rendered == "перезапустіть <term>сервер</term> зараз"


def test_render_wraps_original_text(checker):
    source = "Restart   the SERVER now"
    target = "  Перезапустіть   Сервер зараз"
    [r] = checker.check(source, target, render=True)
    assert r.source_rendered == "Restart   the <term>SERVER</term> now"
    assert r.target_rendered == "  Перезапустіть   <term>Сервер</term> зараз"


def test_render_lemma_only(checker):
    text = "оновіть бази даних"
    [r] = checker.check("update the database", text, render=True)
    assert r.target_rendered == text
    assert r.target_lemmas_rendered == "оновіть <term>база дані</term>"


def test_render_missing(checker):
    text = "перезапустіть машину"
    [r] = checker.check("restart the server", text, render=True)
    assert r.source_rendered == "restart the <term>server</term>"
    assert r.target_rendered == text
    assert r.target_lemmas_rendered == "перезапустіть машину"


# =========================
# Checker: lazy offset maps
# =========================

@pytest.fixture
def build_calls(monkeypatch):
    calls = []
    real_build = OffsetMap.build

    def spy(text, *args, **kwargs):
        calls.append(text)
        return real_build(text, *args, **kwargs)

    monkeypatch.setattr(checker_mod.OffsetMap, "build", spy)
    return calls


def test_offsets_not_built_without_render(checker, build_calls):
    checker.check("restart the server", "перезапустіть сервер")
    assert build_calls == []


def test_offsets_built_once_per_side(checker, build_calls):
    source_text = "restart the server and the database"
    target_text = "перезапустіть сервер і бд"
    results = checker.check(source_text, target_text, render=True)
    assert [r.match_type for r in results] == ["exact", "exact"]
    assert build_calls == [source_text, target_text]


def test_target_offsets_not_built_without_surface_span(checker, build_calls):
    source_text = "restart the server"
    target_text = "перезапустіть машину"
    checker.check(source_text, target_text, render=True)
    assert build_calls == [source_text]
