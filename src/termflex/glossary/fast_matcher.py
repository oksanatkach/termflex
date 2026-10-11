"""Aho-Corasick over lemmas. The automaton is the glossary's only index:
raw terms in; each backend normalizes, tokenizes and lemmatizes its own side."""

from __future__ import annotations

import logging
from dataclasses import dataclass
import ahocorasick

from termflex.utils.doc import Doc
from termflex.lemmatizers import Backend

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class GlossaryTerm:
    source: Doc
    targets: tuple[Doc, ...]


@dataclass(frozen=True)
class SourceMatch:
    term: GlossaryTerm
    token_span: tuple[int, int]            # inclusive token indices; always available
    span: tuple[int, int] | None           # inclusive chars in the normalized text; None if the
    matched_text: str | None               # backend does not expose its tokens


def build_automaton(target_map, source_lemmatizer, target_lemmatizer):
    grouped: dict[str, list[GlossaryTerm]] = {}
    for src, targets in target_map.items():
        source = Doc.from_text(src, source_lemmatizer)
        if not source.tokens:
            log.warning("Skipping glossary term with no word tokens: %r", src)
            continue
        term = GlossaryTerm(
            source=source,
            targets=tuple(Doc.from_text(t, target_lemmatizer) for t in targets),
        )
        grouped.setdefault(source.key, []).append(term)
    if not grouped:
        raise ValueError("No usable glossary terms after lemmatization")

    automaton = ahocorasick.Automaton()
    for key, terms in grouped.items():
        automaton.add_word(key, (key, terms))
    automaton.make_automaton()
    return automaton


def find_matches(automaton: ahocorasick.Automaton, source_text: str, lemmatizer: Backend) -> list[SourceMatch]:
    doc = Doc.from_text(source_text, lemmatizer)
    if not doc.tokens:
        return []
    starts, ends = doc.key_offsets()

    out: list[SourceMatch] = []
    for end_idx, (key, terms) in automaton.iter(doc.key):
        first = starts.get(end_idx - len(key) + 1)
        last = ends.get(end_idx)
        if first is None or last is None:      # not aligned to token boundaries
            continue
        span = doc.span(first, last)
        matched_text = doc.text[span[0]:span[1] + 1] if span else None

        out.extend(SourceMatch(t, (first, last), span, matched_text) for t in terms)
    return out
