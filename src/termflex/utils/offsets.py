"""Map spans in ``normalize(original)`` back to spans in ``original``, so tags can be inserted
into the text exactly as the caller gave it (original case, original Unicode form)."""

from __future__ import annotations

import unicodedata
from bisect import bisect_right
from difflib import SequenceMatcher
from typing import Callable


def _clusters(s: str) -> list[str]:
    """Each character plus its combining marks, so NFC/NFD composition stays inside one cluster."""
    out: list[str] = []
    for ch in s:
        if out and unicodedata.combining(ch):
            out[-1] += ch
        else:
            out.append(ch)
    return out


class OffsetMap:
    """Exact when ``normalize`` works character by character (case, NFC/NFD, ß -> ss, ...).
    For normalizers that collapse whitespace, strip or drop characters it falls back to aligning
    the two strings with difflib: good for those cases, but an approximation."""

    def __init__(self, original: str, norm_starts=None, orig_starts=None, n2o=None, text: str = ""):
        self._original, self._text = original, text
        self._norm, self._orig, self._n2o = norm_starts, orig_starts, n2o

    @property
    def exact(self) -> bool:
        return self._n2o is None

    @classmethod
    def build(cls, original: str, normalize: Callable[[str], str]) -> "OffsetMap":
        text = normalize(original)
        if text == original:
            return cls(original)                                  # identity
        clusters = _clusters(original)
        pieces = [normalize(c) for c in clusters]
        if "".join(pieces) == text:                               # cluster-local: exact mapping
            norm_starts, orig_starts, n, o = [], [], 0, 0
            for c, p in zip(clusters, pieces):
                norm_starts.append(n)
                orig_starts.append(o)
                n += len(p)
                o += len(c)
            return cls(original, norm_starts, orig_starts)
        return cls(original, n2o=_align(original, text), text=text)   # approximate

    def to_original(self, start: int, end: int) -> tuple[int, int]:
        """Inclusive span in the normalized text -> inclusive span in the original,
        widened to whole characters."""
        if self._norm is None and self._n2o is None:
            return start, end
        if self._n2o is not None:
            o, t = self._original, self._text
            s, e = self._n2o[start], self._n2o[end]
            # alignment can't tell which of several collapsed spaces a space came from:
            # snap the edges of a non-space span onto non-space characters
            while s < e and o[s].isspace() and not t[start].isspace():
                s += 1
            while e > s and o[e].isspace() and not t[end].isspace():
                e -= 1
            while e + 1 < len(o) and unicodedata.combining(o[e + 1]):
                e += 1
            return s, e
        ks = bisect_right(self._norm, start) - 1
        ke = bisect_right(self._norm, end) - 1
        stop = self._orig[ke + 1] if ke + 1 < len(self._orig) else len(self._original)
        return self._orig[ks], stop - 1


def _align(original: str, text: str) -> list[int]:
    """For each index of the normalized ``text``, the index of the original character it came from."""
    n2o = [0] * len(text)
    last = max(len(original) - 1, 0)
    lowered = original.lower()
    left = lowered if len(lowered) == len(original) else original   # case-insensitive alignment
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, left, text, autojunk=False).get_opcodes():
        for k in range(j2 - j1):
            if tag == "equal":
                n2o[j1 + k] = i1 + k
            elif tag == "replace":
                n2o[j1 + k] = i1 + min(k, i2 - i1 - 1)
            elif tag == "insert":
                n2o[j1 + k] = min(i1, last)
    return n2o
