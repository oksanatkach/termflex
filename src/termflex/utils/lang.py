"""Language-code parsing for termflex, built on `langcodes`."""

from __future__ import annotations

import re

import langcodes
from langcodes import Language

__all__ = ["InvalidLanguageError", "parse_lang", "validated_lang"]


class InvalidLanguageError(ValueError):
    """Raised when a string cannot be interpreted as a language code."""


def parse_lang(code: "str | Language") -> Language:
    """Parse and validate a language code ("uk", "ukr", "uk_UA", "uk_UA.UTF-8", ...).

    Backends should compare ``parse_lang(code).language`` ("uk") against their
    supported set, so regions, scripts and 3-letter spellings all match.
    """
    if isinstance(code, Language):
        lang = code
    else:
        if not isinstance(code, str) or not code.strip():
            raise InvalidLanguageError(f"Language code must be a non-empty string, got {code!r}.")
        text = re.split(r"[.@]", code.strip(), maxsplit=1)[0]  # drop POSIX suffix
        try:
            lang = Language.get(langcodes.standardize_tag(text))
        except ValueError as e:  # LanguageTagError subclasses ValueError
            raise InvalidLanguageError(f"Cannot parse language code {code!r}: {e}") from e
    if not lang.is_valid():
        raise InvalidLanguageError(f"Unknown language code {code!r}.")
    return lang


def validated_lang(lang: str) -> Language:
    lang = parse_lang(lang)  # fail fast on bad codes, store canonical tags

    if not isinstance(lang.language, str) or len(lang.language) == 0:
        raise InvalidLanguageError("Could not parse the source language name")

    return lang
