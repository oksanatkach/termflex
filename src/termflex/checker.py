from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from termflex import Glossary
from termflex.utils.doc import Doc
from termflex.utils.offsets import OffsetMap
from termflex.utils.utils import find_seq, find_subphrase

TAG = "term"

Span = tuple[int, int]


# =========================
# Core match (evaluation)
# =========================

@dataclass(frozen=True)
class TermMatch:
    source_term: str
    expected_targets: list[str]

    found_targets: list[str]
    match: bool

    match_type: str  # "exact" | "lemma" | "surface" | "missing"

    source_span: Optional[Span]          # character span (normalized coordinates)
    target_span: Optional[Span]          # character span (normalized coordinates)

    source_lemma_span: Optional[Span]    # token span
    target_lemma_span: Optional[Span]    # token span

    source_lemmas: list[str]
    target_lemmas: Optional[list[str]]


# =========================
# Rendered variant
# =========================

@dataclass(frozen=True)
class RenderedTermMatch(TermMatch):
    source_rendered: Optional[str] = None
    target_rendered: Optional[str] = None

    source_lemmas_rendered: Optional[str] = None
    target_lemmas_rendered: Optional[str] = None


# =========================
# Helpers
# =========================

def wrap_lemmas(lemmas: Sequence[str], first: int, last: int, tag: str = TAG) -> str:
    parts = list(lemmas)
    parts[first] = f"<{tag}>{parts[first]}"
    parts[last] = f"{parts[last]}</{tag}>"
    return " ".join(parts)


def wrap_text(text: str, span: Span, offsets: OffsetMap, tag: str = TAG) -> str:
    s, e = offsets.to_original(*span)
    return f"{text[:s]}<{tag}>{text[s:e + 1]}</{tag}>{text[e + 1:]}"


def _lazy(factory: Callable):
    cache = []

    def get():
        if not cache:
            cache.append(factory())
        return cache[0]

    return get


# A candidate keeps BOTH spans separately:
#   (target original text, match type, lemma span [tokens], surface span [chars])
Candidate = tuple[str, str, Optional[Span], Optional[Span]]

_PRIORITY = {"exact": 3, "lemma": 2, "surface": 1}


# =========================
# Checker
# =========================

class Checker:
    def __init__(self, glossary: Glossary) -> None:
        self.glossary = glossary

    def check(
        self,
        source_text: str,
        target_text: str,
        render: bool = False
    ) -> list[TermMatch] | list[RenderedTermMatch]:

        matches = self.glossary.find_terms(source_text)
        if not matches:
            return []

        src_lem = self.glossary.source_lemmatizer
        tgt_lem = self.glossary.target_lemmatizer

        source_doc = Doc.from_text(source_text, src_lem)
        target_doc = Doc.from_text(target_text, tgt_lem)
        target_norm = target_doc.text

        src_offsets = _lazy(lambda: OffsetMap.build(source_text, src_lem.normalize))
        tgt_offsets = _lazy(lambda: OffsetMap.build(target_text, tgt_lem.normalize))

        results: list[TermMatch | RenderedTermMatch] = []

        for match in matches:
            term = match.term

            found_targets: list[str] = []
            candidates: list[Candidate] = []

            best_match_type = "missing"
            best_surface_span: Optional[Span] = None  # character span
            best_lemma_span: Optional[Span] = None    # token span

            # -------------------------
            # matching phase
            # -------------------------
            for t in term.targets:
                i = find_seq(target_doc.lemmas, t.lemmas)
                surface = find_subphrase(target_norm, t.text)

                if i is None and surface is None:
                    continue

                if i is not None and surface is not None:
                    match_type = "exact"
                elif i is not None:
                    match_type = "lemma"
                else:
                    match_type = "surface"

                lemma_span = (i, i + len(t.lemmas) - 1) if i is not None else None

                # keep the two spans separate: token indices vs. character offsets
                candidates.append((t.original, match_type, lemma_span, surface))

            match_flag = bool(candidates)

            # -------------------------
            # select best candidate
            # -------------------------
            if candidates:
                best = max(candidates, key=lambda c: _PRIORITY[c[1]])

                found_targets = [c[0] for c in candidates]
                _, best_match_type, best_lemma_span, best_surface_span = best

            # -------------------------
            # base object
            # -------------------------
            base = TermMatch(
                source_term=term.source.original,
                expected_targets=[t.original for t in term.targets],

                found_targets=found_targets,
                match=match_flag,

                match_type=best_match_type,

                source_span=match.span,
                target_span=best_surface_span,

                source_lemma_span=match.token_span,
                target_lemma_span=best_lemma_span,

                source_lemmas=source_doc.lemmas,
                target_lemmas=target_doc.lemmas if match_flag else None,
            )

            if not render:
                results.append(base)
                continue

            # -------------------------
            # rendering phase
            # -------------------------

            # surface rendering (full context preserved)
            source_rendered = (
                wrap_text(source_text, match.span, src_offsets())
                if match.span else None
            )

            target_rendered = (
                wrap_text(target_text, best_surface_span, tgt_offsets())
                if best_surface_span else target_text
            )

            # lemma rendering (debug / QA)
            source_lemmas_rendered = (
                wrap_lemmas(
                    source_doc.lemmas,
                    match.token_span[0],
                    match.token_span[1]
                )
                if match.token_span else " ".join(source_doc.lemmas)
            )

            target_lemmas_rendered = (
                wrap_lemmas(
                    target_doc.lemmas,
                    best_lemma_span[0],
                    best_lemma_span[1]
                )
                if best_lemma_span else " ".join(target_doc.lemmas)
            )

            results.append(
                RenderedTermMatch(
                    **base.__dict__,
                    source_rendered=source_rendered,
                    target_rendered=target_rendered,
                    source_lemmas_rendered=source_lemmas_rendered,
                    target_lemmas_rendered=target_lemmas_rendered,
                )
            )

        return results
