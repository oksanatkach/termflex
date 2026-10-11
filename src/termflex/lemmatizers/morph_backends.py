"""Lemmatizer backends: one interface, a registry, and per-language validation."""

from __future__ import annotations

import importlib
import os
import re
import sys
from functools import lru_cache
from typing import Callable, ClassVar, Iterable
import logging
from langcodes import Language
import threading
from importlib.metadata import entry_points

from termflex.utils.utils import default_normalize
from termflex.utils.lang import parse_lang, validated_lang, InvalidLanguageError

logger = logging.getLogger(__name__)

__all__ = [
    "Backend", "UnsupportedLanguageError", "register_backend", "register_function",
    "get_backend", "available_backends", "backends_for", "resolve_backend_spec",
]

ENTRY_POINT_GROUP = "termflex.lemmatizers"


class UnsupportedLanguageError(ValueError):
    """The chosen backend cannot handle the requested language."""


_REGISTRY: dict[str, type["Backend"]] = {}
_INSTANCES: dict[tuple, Backend] = {}
_INSTANCES_LOCK = threading.RLock()      # reentrant: a backend constructor may trigger plugin loading

_PLUGINS_LOADED = False                  # True once every entry point has been tried (or failed)
_PLUGINS_LOADING = False                 # True while a plugin import is in progress (re-entry guard)
_PLUGINS_LOCK = threading.RLock()


def clear_backend_cache() -> None:
    """For tests: forget all cached backend instances."""
    with _INSTANCES_LOCK:
        _INSTANCES.clear()


def register_backend(cls: type["Backend"]) -> type["Backend"]:
    if cls.name in _REGISTRY:
        raise ValueError(f"Backend {cls.name!r} is already registered.")
    _REGISTRY[cls.name] = cls
    return cls


def register_function(name=None, *, languages=None):
    """Decorator: register fn(text, lang_code) -> list[str] | str as a named backend.

        @register_function                                   # backend name = function name
        @register_function("hunspell-r", languages={"uk"})   # explicit name / languages
    """
    def decorate(fn, backend_name):
        def __init__(self, lang, normalize, tokenize=None):
            CallableBackend.__init__(self, fn, lang, normalize, tokenize)

        register_backend(type(f"FunctionBackend[{backend_name}]", (CallableBackend,), {
            "name": backend_name,
            "languages": frozenset(languages) if languages else None,
            "__init__": __init__,
        }))
        return fn                       # the function stays an ordinary callable function

    if callable(name):                  # bare @register_function
        return decorate(name, name.__name__)
    return lambda fn: decorate(fn, name or fn.__name__)


def _load_plugins() -> None:
    """Import every module advertised under the ``termflex.lemmatizers`` entry-point group.

    Importing a plugin module runs its ``@register_backend`` / ``@register_function`` decorators,
    which is what actually registers the backends. Runs at most once per process, lazily: only when
    a backend name is not found, or when the registry is listed. A plugin that fails to import is
    logged and skipped; it never stops the others.
    """
    global _PLUGINS_LOADED, _PLUGINS_LOADING
    if _PLUGINS_LOADED:
        return
    with _PLUGINS_LOCK:
        if _PLUGINS_LOADED or _PLUGINS_LOADING:   # LOADING: a plugin's import called back into us
            return
        _PLUGINS_LOADING = True
        try:
            for ep in entry_points(group=ENTRY_POINT_GROUP):
                try:
                    ep.load()
                except Exception:
                    logger.warning("Could not load termflex backend plugin %r (%s)",
                                   ep.name, ep.value, exc_info=True)
        finally:
            _PLUGINS_LOADING = False
            _PLUGINS_LOADED = True


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

    @classmethod
    def cache_key(cls, lang) -> str:
        """What makes two requests equivalent for this backend. Default: the language code."""
        return lang.language

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
    cls = _REGISTRY.get(spec)
    if cls is None:
        _load_plugins()                 # the name may come from an installed plugin
        cls = _REGISTRY.get(spec)
    if cls is None:
        raise ValueError(f"Unknown backend {spec!r}. Available: {', '.join(sorted(_REGISTRY))}.")

    key = (cls, cls.cache_key(lang), normalize, tokenize)
    try:
        hash(key)
    except TypeError:               # an unhashable callable: skip the cache
        return cls(lang, normalize, tokenize)

    with _INSTANCES_LOCK:
        inst = _INSTANCES.get(key)
        if inst is None:
            inst = _INSTANCES[key] = cls(lang, normalize, tokenize)
    return inst


def available_backends() -> dict[str, list[str] | None]:
    """{"pymorphy3": ["ru", "uk"], "simplemma": [...] or None if unknown}"""
    _load_plugins()
    out = {}
    for name, cls in sorted(_REGISTRY.items()):
        langs = cls.supported_languages()
        out[name] = sorted(langs) if langs is not None else None
    return out


def backends_for(lang) -> list[str]:
    """Names of registered backends that can handle ``lang`` (unknown-support ones included)."""
    _load_plugins()
    lang = validated_lang(lang).language
    return [name for name, cls in sorted(_REGISTRY.items()) if cls.supports(lang)]


def resolve_backend_spec(spec: str):
    """Turn a command-line style string into something ``get_backend`` / ``Glossary`` accepts.

    ``"auto"``              -> ``"auto"`` (passed through untouched)
    ``"pymorphy3"``         -> ``"pymorphy3"`` (a registered backend name, checked to exist)
    ``"my_mod:my_func"``    -> the function ``my_func`` (used as a custom lemmatizer, nothing registered)
    ``"my_mod:MyBackend"``  -> the registered name of the ``Backend`` subclass (registered here if the
                               module did not already do it with ``@register_backend``)

    The module is imported from the installed environment or the current directory, so any
    ``@register_backend`` / ``@register_function`` decorators in it run as a side effect.
    """
    if not isinstance(spec, str) or not spec.strip():
        raise ValueError("empty backend specification")
    spec = spec.strip()

    if spec == "auto":
        return spec

    if ":" not in spec:
        _load_plugins()
        if spec not in _REGISTRY:
            raise ValueError(f"Unknown backend {spec!r}. Available: {', '.join(sorted(_REGISTRY))}, auto; "
                             f"or give a 'module:name' path.")
        return spec

    module_name, _, attr_path = spec.partition(":")
    if not (module_name and attr_path and all(part.isidentifier() for part in module_name.split("."))
            and all(part.isidentifier() for part in attr_path.split("."))):
        raise ValueError(f"Invalid backend path {spec!r}: expected 'package.module:name'.")

    cwd = os.getcwd()
    if cwd not in sys.path:         # like gunicorn / uvicorn: let people point at a file next to them
        sys.path.insert(0, cwd)
    try:
        obj = importlib.import_module(module_name)
    except ImportError as e:
        raise ImportError(f"Cannot import module {module_name!r} from {spec!r}: {e}") from e
    for part in attr_path.split("."):
        try:
            obj = getattr(obj, part)
        except AttributeError:
            raise ValueError(f"Module {module_name!r} has no attribute {attr_path!r}.") from None

    if isinstance(obj, type) and issubclass(obj, Backend):
        name = getattr(obj, "name", None)
        if not isinstance(name, str) or not name:
            raise ValueError(f"{spec!r}: Backend subclasses need a 'name' class attribute.")
        existing = _REGISTRY.get(name)
        if existing is None:
            register_backend(obj)
        elif existing is not obj:
            raise ValueError(f"{spec!r}: the backend name {name!r} is already used by another backend.")
        return name
    if isinstance(obj, Backend):
        raise ValueError(f"{spec!r} is a Backend instance; instances are tied to one language. "
                         f"Point at the class or at a function instead.")
    if callable(obj):
        return obj
    raise ValueError(f"{spec!r} is neither a Backend subclass nor a function.")
