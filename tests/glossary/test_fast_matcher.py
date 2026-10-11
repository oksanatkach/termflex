"""Unit tests for the Aho-Corasick lemma matcher: build_automaton and find_matches."""
from __future__ import annotations

import logging
import re

import pytest

from termflex.glossary.fast_matcher import GlossaryTerm, SourceMatch, build_automaton, find_matches
from termflex.lemmatizers import Backend

from tests import en_lem, uk_lem


class LemmasOnlyBackend(Backend):
    """Hides its tokenizer (tokenize=None), so Docs carry lemmas but no character spans."""

    name = "lemmas-only"
    _TOKEN = re.compile(r"\w+")

    def __init__(self, lang, table=None):
        self.table = table or {}
        super().__init__(lang, normalize=None, tokenize=None)

    def _lemmatize(self, text):
        return [self.table.get(t, t) for t in self._TOKEN.findall(text)]


class MismatchedBackend(Backend):
    """tokenize() and lemmatize() disagree on token count; Doc falls back to lemmas only."""

    name = "mismatched"

    def __init__(self, lang):
        super().__init__(lang, normalize=None, tokenize=lambda s: [s])   # whole string = 1 token

    def _lemmatize(self, text):
        return text.split()


def build(target_map, src=en_lem, tgt=uk_lem):
    return build_automaton(target_map, src, tgt)


def match(target_map, text, src=en_lem):
    return find_matches(build(target_map, src=src), text, src)


# =========================
# build_automaton
# =========================


def test_automaton_keys_are_source_lemmas():
    auto = build({"Servers": ["сервер"], "database server": ["сервер бази даних"]})
    assert set(auto.keys()) == {"server", "database server"}


def test_targets_are_lemmatized_with_target_lemmatizer():
    key, terms = build({"database": ["бази даних", "бд"]}).get("database")
    assert key == "database"
    (term,) = terms
    assert isinstance(term, GlossaryTerm)
    assert term.source.original == "database"
    assert [t.original for t in term.targets] == ["бази даних", "бд"]     # order kept
    assert [t.lemmas for t in term.targets] == [("база", "дані"), ("бд",)]


def test_sources_with_same_lemmas_share_one_key():
    auto = build({"server": ["сервер"], "servers": ["хост"], "SERVER": ["вузол"]})
    assert list(auto.keys()) == ["server"]
    _, terms = auto.get("server")
    assert [t.source.original for t in terms] == ["server", "servers", "SERVER"]   # insertion order
    assert [t.targets[0].original for t in terms] == ["сервер", "хост", "вузол"]


def test_empty_target_list_is_allowed():
    _, (term,) = build({"server": []}).get("server")
    assert term.targets == ()


def test_source_without_word_tokens_is_skipped_with_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="termflex.glossary.fast_matcher"):
        auto = build({"---": ["x"], "server": ["сервер"]})
    assert list(auto.keys()) == ["server"]
    assert "'---'" in caplog.text


@pytest.mark.parametrize("target_map", [{}, {"": ["x"]}, {"  !! ": ["x"], "...": ["y"]}])
def test_no_usable_terms_raises(target_map):
    with pytest.raises(ValueError, match="No usable glossary terms"):
        build(target_map)


# =========================
# find_matches: basics
# =========================


def test_inflected_form_matches_with_offsets():
    text = "Restart the SERVERS now"
    (m,) = match({"server": ["сервер"]}, text)
    assert isinstance(m, SourceMatch)
    assert m.token_span == (2, 2)
    assert m.span == (12, 18)                # inclusive, into the normalized text
    assert m.matched_text == "servers"      # normalized (lowercased), not the original casing
    assert text.lower()[m.span[0]:m.span[1] + 1] == m.matched_text
    assert m.term.targets[0].original == "сервер"


def test_multiword_term():
    (m,) = match({"database server": ["x"]}, "Our database servers are down")
    assert (m.token_span, m.span, m.matched_text) == ((1, 2), (4, 19), "database servers")


def test_every_occurrence_is_reported_in_text_order():
    ms = match({"server": ["x"], "database": ["y"]}, "server, database and servers")
    assert [(m.term.source.key, m.token_span) for m in ms] == [
        ("server", (0, 0)), ("database", (1, 1)), ("server", (3, 3)),
    ]


def test_overlapping_terms_all_match():
    ms = match({"database": ["x"], "server": ["y"], "database server": ["z"]}, "the database server")
    assert sorted((m.term.source.key, m.token_span) for m in ms) == [
        ("database", (1, 1)), ("database server", (1, 2)), ("server", (2, 2)),
    ]


def test_one_match_per_grouped_term():
    ms = match({"server": ["сервер"], "servers": ["хост"]}, "a server")
    assert [m.term.source.original for m in ms] == ["server", "servers"]
    assert {m.token_span for m in ms} == {(1, 1)}


@pytest.mark.parametrize("text", ["", "   ", "--- !!! ...", "nothing relevant here"])
def test_no_matches(text):
    assert match({"server": ["x"]}, text) == []


def test_cyrillic_source():
    (m,) = match({"база даних": ["database"]}, "Немає бази даних.", src=uk_lem)
    assert (m.token_span, m.matched_text) == ((1, 2), "бази даних")


# =========================
# find_matches: token boundaries and gaps
# =========================


@pytest.mark.parametrize("text", ["observer", "serverless", "webserver farm"])
def test_no_match_inside_a_word(text):
    assert match({"server": ["x"]}, text) == []


def test_partial_multiword_does_not_match():
    assert match({"database server": ["x"]}, "the database is up") == []


def test_whitespace_runs_and_newlines_are_equivalent():
    (m,) = match({"database server": ["x"]}, "database \n\t  server")
    assert m.token_span == (0, 1)
    assert m.matched_text == "database server"     # normalize() collapsed the whitespace


def test_hyphen_is_normalized_to_space():
    (m,) = match({"database server": ["x"]}, "a database-server")
    assert m.token_span == (1, 2)


def test_punctuation_between_tokens_blocks_match():
    # the gap is part of the key: "database. server" != "database server"
    assert match({"database server": ["x"]}, "the database. Server") == []


def test_punctuation_inside_term_must_match():
    ms = match({"order. system": ["x"]}, "order. system and order system")
    assert [m.token_span for m in ms] == [(0, 1)]


# =========================
# find_matches: backends without spans
# =========================


def test_lemmas_only_backend_has_token_span_but_no_chars():
    lem = LemmasOnlyBackend("en", {"servers": "server"})
    (m,) = find_matches(build_automaton({"server": ["x"]}, lem, lem), "Two servers", lem)
    assert (m.token_span, m.span, m.matched_text) == ((1, 1), None, None)


def test_lemmas_only_backend_ignores_punctuation_gaps():
    # no gap information, so tokens are joined with single spaces on both sides
    lem = LemmasOnlyBackend("en")
    ms = find_matches(build_automaton({"database server": ["x"]}, lem, lem), "database. server", lem)
    assert [m.token_span for m in ms] == [(0, 1)]


def test_tokenize_lemmatize_mismatch_falls_back_to_lemmas_only():
    lem = MismatchedBackend("en")
    (m,) = find_matches(build_automaton({"database server": ["x"]}, lem, lem), "big database server", lem)
    assert (m.token_span, m.span, m.matched_text) == ((1, 2), None, None)


def test_automaton_is_reusable_across_texts():
    auto = build({"server": ["x"]})
    assert [m.token_span for m in find_matches(auto, "server", en_lem)] == [(0, 0)]
    assert [m.token_span for m in find_matches(auto, "no match", en_lem)] == []
    assert [m.token_span for m in find_matches(auto, "a b servers", en_lem)] == [(2, 2)]
