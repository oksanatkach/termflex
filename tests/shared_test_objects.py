"""Test objects shared by the checker and glossary tests."""
from __future__ import annotations

import json
import re

from termflex.lemmatizers import Backend


class ToyBackend(Backend):
    """Deterministic per-token lemmatizer: \\w+ tokens + a lookup table."""

    name = "toy"
    _TOKEN = re.compile(r"\w+")

    def __init__(self, lang, table=None):
        self.table = table or {}
        super().__init__(lang, normalize=None, tokenize=self._TOKEN.findall)

    def _lemmatize(self, text):
        return [self.table.get(tok.casefold(), tok) for tok in self.tokenize(text)]


en_lem = ToyBackend("en", {"servers": "server", "databases": "database"})
uk_lem = ToyBackend("uk", {"сервера": "сервер", "бази": "база", "даних": "дані"})

# one target per source: expressible in every format, PO included
PAIRS = [("server", "сервер"), ("database", "база даних")]
# several targets per source (repeat the source): CSV, JSON, TBX
MULTI = [
    ("server", "сервер"),
    ("server", "хост"),
    ("database", "база даних"),
    ("database", "бд"),
]

GLOSSARY_JSON = {"terms": [{"en": s, "uk": t} for s, t in PAIRS]}
SCHEMA = {"root": "terms", "source": "en", "target": "uk"}
