"""Result of ``Backend.analyze``: normalized text plus one (span, lemma) per token.

This is a plain data holder. Backends own normalization and tokenization; it exists
only so a match found in the lemma stream can be mapped back to character offsets.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cached_property
from typing import NamedTuple
import logging

_WS = re.compile(r"\s+")

logger = logging.getLogger(__name__)


class Token(NamedTuple):
    lemma: str
    start: int | None = None   # inclusive, offset into Doc.text; None if the backend hides its tokens
    end: int | None = None     # exclusive
    text: str | None = None


def align_tokens(text, words):
    """Spans for tokens that are verbatim substrings of `text`, in order."""
    spans, pos = [], 0
    for w in words:
        i = text.find(w, pos)
        if i < 0:
            raise ValueError(f"Token {w!r} not found in text after position {pos}")
        spans.append((i, i + len(w)))
        pos = i + len(w)
    return spans


@dataclass(frozen=True)
class Doc:
    original: str                  # exactly as given (glossary term, input text, ...)
    text: str                      # backend.normalize(original); all offsets index into this
    tokens: tuple[Token, ...]

    @property
    def lemmas(self) -> tuple[str, ...]:
        return tuple(t.lemma for t in self.tokens)

    @property
    def has_spans(self) -> bool:
        """False for backends that only return lemmas (their tokenizer is not exposed)."""
        return all(t.start is not None for t in self.tokens)

    @cached_property
    def _parts(self) -> tuple[str, tuple[tuple[int, int], ...]]:
        """(key, [(first_char, last_char) of each lemma within key])."""
        pieces: list[str] = []
        bounds: list[tuple[int, int]] = []
        pos = 0
        for i, tok in enumerate(self.tokens):
            if i:
                # Keep what separates two tokens: whitespace runs collapse to one space, adjacent
                # tokens stay adjacent. "order. System" != "order system"; "C++" stays "c++".
                gap = (_WS.sub(" ", self.text[self.tokens[i - 1].end:tok.start])
                       if self.has_spans else " ")   # lemmas-only: no gap information
                pieces.append(gap)
                pos += len(gap)
            bounds.append((pos, pos + len(tok.lemma) - 1))
            pieces.append(tok.lemma)
            pos += len(tok.lemma)
        return "".join(pieces), tuple(bounds)

    @property
    def key(self) -> str:
        """Automaton key: lemmas separated by their whitespace-normalized gaps."""
        return self._parts[0]

    def key_offsets(self) -> tuple[dict[int, int], dict[int, int]]:
        """Map key positions to token indices: ({first_char: i}, {last_char: i})."""
        bounds = self._parts[1]
        return {a: i for i, (a, _) in enumerate(bounds)}, {b: i for i, (_, b) in enumerate(bounds)}

    def span(self, first: int, last: int) -> tuple[int, int] | None:
        """Inclusive character span in ``text`` for tokens first..last (None without spans)."""
        if not self.has_spans:
            return None
        return self.tokens[first].start, self.tokens[last].end - 1

    @classmethod
    def from_text(cls, original: str, lemmatizer) -> "Doc":
        norm = lemmatizer.normalize(original)
        lemmas = lemmatizer.lemmatize(norm)              # whole string, one call

        if not lemmatizer.tokenize:                      # tokens hidden: lemmas only
            tokens = tuple(Token(lemma=l) for l in lemmas)
        else:
            words = lemmatizer.tokenize(norm)
            if len(words) != len(lemmas):
                logger.debug(
                    f"tokenize() gave {len(words)} tokens but lemmatize() gave {len(lemmas)} lemmas; "
                    "they must use the same tokenization."
                    "Will only use lemmas.")
                tokens = tuple(Token(lemma=l) for l in lemmas)
            else:
                spans = align_tokens(norm, words)
                tokens = tuple(
                    Token(lemma=l, start=s, end=e, text=w)
                    for (s, e), w, l in zip(spans, words, lemmas)
                )
        return cls(original=original, text=norm, tokens=tokens)

    def char_span(self, first: int, last: int) -> tuple[int, int] | None:
        """Inclusive character span in ``text`` for tokens first..last; None without spans."""
        if not self.has_spans:
            return None
        return self.tokens[first].start, self.tokens[last].end - 1
