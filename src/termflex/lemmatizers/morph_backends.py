"""Lemmatizer backends: one interface, a registry, and per-language validation."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Callable, ClassVar, Iterable
import logging
from langcodes import Language

from termflex.utils.utils import default_normalize
from termflex.utils.lang import parse_lang, validated_lang, InvalidLanguageError

logger = logging.getLogger(__name__)

__all__ = [
    "Backend", "UnsupportedLanguageError", "register_backend",
    "get_backend", "available_backends", "backends_for",
]


class UnsupportedLanguageError(ValueError):
    """The chosen backend cannot handle the requested language."""

_REGISTRY: dict[str, type["Backend"]] = {}

def register_backend(cls: type["Backend"]) -> type["Backend"]:
    if cls.name in _REGISTRY:
        raise ValueError(f"Backend {cls.name!r} is already registered.")
    _REGISTRY[cls.name] = cls
    return cls


def _missing(name: str, extra: str) -> ImportError:
    return ImportError(f"Backend {name!r} needs extra dependencies: pip install 'termflex[{extra}]'")


class Backend:
    """Base class. Subclasses implement ``_lemmatize`` and declare ``languages``."""

    name: ClassVar[str]
    extra: ClassVar[str | None] = None                 # pip extra that installs the dependencies
    languages: ClassVar[frozenset[str] | None] = None  # ISO 639-1 base codes; None = any

    def __init__(self, lang: "str | Language", normalize: Callable | None, tokenize: Callable | None):
        self.lang = parse_lang(lang) if isinstance(lang, str) else lang
        self.lang_code = self.lang.language                 # "uk" for "uk_UA", "ukr", ...
        self.normalize = normalize if normalize else default_normalize
        self.tokenize = tokenize

        if not isinstance(self.lang_code, str) or len(self.lang_code) == 0:
            raise InvalidLanguageError("Could not parse the source language name")
        if not self.supports(self.lang):
            raise UnsupportedLanguageError(self._unsupported_message(lang))

    @classmethod
    def supported_languages(cls) -> frozenset[str] | None:
        return cls.languages

    @classmethod
    def supports(cls, lang) -> bool:
        supported = cls.supported_languages()
        return supported is None or parse_lang(lang).language in supported

    def _unsupported_message(self, lang) -> str:
        supported = ", ".join(sorted(self.supported_languages() or ()))
        alternatives = [n for n in backends_for(self.lang) if n != self.name]
        hint = f" Backends that support it: {', '.join(alternatives)}." if alternatives else ""
        return f"Backend {self.name!r} supports only {supported}; got {str(lang)!r}.{hint}"

    def lemmatize(self, text: str) -> list[str]:
        """Public entry point: lemmas for every token in ``text``, casefolded."""
        text = self.normalize(text)
        return [lemma.casefold() for lemma in self._lemmatize(text)]

    def _lemmatize(self, text: str) -> Iterable[str]:
        raise NotImplementedError


@register_backend
class Pymorphy3Backend(Backend):
    name = "pymorphy3"
    extra = "pymorphy3"
    languages = frozenset({"uk", "ru"})

    # pymorphy3 does not tokenize; keep internal apostrophes/hyphens (п'ять, кросс-платформа)
    _TOKEN = re.compile(r"\w+(?:[’'ʼ-]\w+)*")

    def __init__(self, lang: str, normalize: Callable | None, tokenize: Callable | None = None):
        tokenize = tokenize if tokenize else self._tokenize
        super().__init__(lang, normalize, tokenize)
        try:
            import pymorphy3
        except ImportError as e:
            raise _missing(self.name, self.extra) from e
        try:
            morph = pymorphy3.MorphAnalyzer(lang=self.lang_code)
        except ValueError as e:         # language is supported, so the dictionary package is missing
            raise _missing(self.name, self.extra) from e
        self._lemma = lru_cache(maxsize=100_000)(lambda word: morph.parse(word)[0].normal_form)

    def _lemmatize(self, text: str) -> list[str]:
        return [self._lemma(tok) for tok in self.tokenize(text)]

    def _tokenize(self, text: str) -> list[str]:
        return self._TOKEN.findall(text)


@register_backend
class SimplemmaBackend(Backend):
    name = "simplemma"
    extra = "simplemma"

    @classmethod
    def supported_languages(cls) -> frozenset[str] | None:
        # Uses simplemma's own list when installed; None (= unknown) otherwise.
        try:
            from simplemma.strategies.dictionaries.dictionary_factory import SUPPORTED_LANGUAGES
            return frozenset(SUPPORTED_LANGUAGES)
        except Exception:
            return None

    def __init__(self, lang: "str | Language", normalize: Callable | None, tokenize: Callable | None):
        super().__init__(lang, normalize, tokenize)
        try:
            import simplemma
        except ImportError as e:
            raise _missing(self.name, self.extra) from e
        try:
            simplemma.text_lemmatizer("", lang=self.lang_code)   # probe: raises ValueError if unsupported
        except ValueError as e:
            raise UnsupportedLanguageError(self._unsupported_message(lang)) from e
        self._simplemma = simplemma

    def _lemmatize(self, text: str) -> list[str]:
        if self.tokenize:
            return [self._simplemma.lemmatize(token, lang=self.lang_code) for token in self.tokenize(text)]
        return self._simplemma.text_lemmatizer(text, lang=self.lang_code)


class CallableBackend(Backend):
    """Wraps a user function ``fn(text, lang_code) -> list[str]`` (or a single str)."""

    name = "custom"

    def __init__(self, fn: Callable[[str, str], "str | Iterable[str]"], lang: "str | Language",
                 normalize: Callable | None,
                 tokenize: Callable | None):
        self._fn = fn
        super().__init__(lang, normalize, tokenize)

    def _lemmatize(self, text: str) -> list[str]:
        if self.tokenize:
            out = [self._fn(token, self.lang_code) for token in self.tokenize(text)]
        else:
            out = self._fn(text, self.lang_code)
        return [out] if isinstance(out, str) else list(out)


def get_backend(spec: "str | Callable | Backend",
                lang: "str | Language",
                normalize: Callable | None = None,
                tokenize: Callable | None = None) -> Backend:
    """Resolve a backend name, custom callable, or ready-made instance for ``lang``."""
    if isinstance(lang, str):
        lang = parse_lang(lang)
    if not isinstance(lang.language, str) or len(lang.language) == 0:
        raise InvalidLanguageError("Could not parse the source language name")

    if isinstance(spec, Backend):
        if spec.lang_code != lang.language:
            raise UnsupportedLanguageError(
                f"Backend instance was built for {spec.lang_code!r}, but {str(lang)!r} was requested.")
        return spec
    if callable(spec):
        return CallableBackend(spec, lang, normalize, tokenize)
    try:
        cls = _REGISTRY[spec]
    except KeyError:
        raise ValueError(f"Unknown backend {spec!r}. Available: {', '.join(sorted(_REGISTRY))}.") from None
    return cls(lang, normalize, tokenize)


def available_backends() -> dict[str, list[str] | None]:
    """{"pymorphy3": ["ru", "uk"], "simplemma": [...] or None if unknown}"""
    out = {}
    for name, cls in sorted(_REGISTRY.items()):
        langs = cls.supported_languages()
        out[name] = sorted(langs) if langs is not None else None
    return out


def backends_for(lang) -> list[str]:
    """Names of registered backends that can handle ``lang`` (unknown-support ones included)."""
    lang = validated_lang(lang).language
    return [name for name, cls in sorted(_REGISTRY.items()) if cls.supports(lang)]
