from __future__ import annotations
from dataclasses import dataclass
from typing import Callable
from langcodes import Language
import logging
from functools import partial

from termflex.utils.lang import validated_lang
from termflex.glossary.loaders import (parse_tbx_to_term_map,
                                       parse_csv_to_term_map,
                                       parse_json_to_term_map,
                                       parse_po_to_term_map)
from termflex.glossary.fast_matcher import build_automaton, find_matches
from termflex.lemmatizers import get_backend, Backend, UnsupportedLanguageError
from termflex.utils.utils import default_normalize

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceMatch:
    src_term: str
    targets: list[str]
    target_lemmas: list[list[str]]
    span: tuple[int, int]


def _resolve(spec, lang, normalize, tokenize) -> Backend:
    if spec == 'auto':
        spec = 'simplemma'
    try:
        return get_backend(spec, lang, normalize, tokenize)
    except UnsupportedLanguageError as e:
        raise UnsupportedLanguageError(f"Language is not supported: {e}") from e


class Glossary(object):
    def __init__(self, automaton, target_map, source_lang: Language, target_lang: Language,
                 source_lemmatizer: Backend, target_lemmatizer: Backend):
        self.automaton = automaton
        self.target_map = target_map
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.source_lemmatizer = source_lemmatizer
        self.target_lemmatizer = target_lemmatizer

        if source_lang.language == 'ru' or target_lang.language == 'ru':
            logger.critical(r"""
                                _         _               _                           _     _         _        _       
                               (_)       (_)             | |                         (_)   | |       | |      | |      
             _ __ _   _ ___ ___ _  __ _   _ ___    __ _  | |_ ___ _ __ _ __ ___  _ __ _ ___| |_   ___| |_ __ _| |_ ___ 
            | '__| | | / __/ __| |/ _` | | / __|  / _` | | __/ _ \ '__| '__/ _ \| '__| / __| __| / __| __/ _` | __/ _ \
            | |  | |_| \__ \__ \ | (_| | | \__ \ | (_| | | ||  __/ |  | | | (_) | |  | \__ \ |_  \__ \ || (_| | ||  __/
            |_|   \__,_|___/___/_|\__,_| |_|___/  \__,_|  \__\___|_|  |_|  \___/|_|  |_|___/\__| |___/\__\__,_|\__\___|


            """)

    @classmethod
    def _build(cls,
               parser: Callable,
               source_lang: str,
               target_lang: str,
               lemmatizer: str | Backend = 'simplemma',
               source_lemmatizer: None | str | Backend = None,
               target_lemmatizer: None | str | Backend = None,
               normalize: Callable = default_normalize,
               tokenize: Callable = None) -> "Glossary":

        source_lang = validated_lang(source_lang)
        target_lang = validated_lang(target_lang)

        target_map = parser()

        if not target_map:   # moved before build_automaton
            raise ValueError("The glossary does not contain any terms in both the source and target languages")

        # Resolve (and validate) both backends before doing any file work.
        source_lemmatizer = _resolve(source_lemmatizer or lemmatizer, source_lang, normalize, tokenize)
        target_lemmatizer = _resolve(target_lemmatizer or lemmatizer, target_lang, normalize, tokenize)

        automaton = build_automaton(
            target_map=target_map,
            source_lemmatizer=source_lemmatizer,
            target_lemmatizer=target_lemmatizer
        )
        return cls(automaton, target_map, source_lang, target_lang, source_lemmatizer, target_lemmatizer)

    @classmethod
    def from_tbx(cls, file_path, source_lang, target_lang, **kwargs):
        parser = partial(
            parse_tbx_to_term_map,
            path=file_path,
            source_lang=source_lang,
            target_lang=target_lang,
        )
        return cls._build(parser, source_lang, target_lang, **kwargs)

    @classmethod
    def from_po(cls, file_path, source_lang, target_lang, **kwargs):
        parser = partial(
            parse_po_to_term_map,
            file_path=file_path,
        )
        return cls._build(parser, source_lang, target_lang, **kwargs)

    @classmethod
    def from_csv(cls,
                 file_path,
                 source_term_column,
                 target_term_column,
                 source_lang,
                 target_lang,
                 delimiter=None,
                 newline=None,
                 encoding=None,
                 **kwargs):
        '''
        CSV should look like:

        en,fr
        federated database,base de données fédérée
        federated database,base fédérée
        distributed system,système distribué
        '''
        optional = {
            "delimiter": delimiter,
            "newline": newline,
            "encoding": encoding,
        }

        parser_kwargs = {
            "source_col": source_term_column,
            "target_col": target_term_column,
            **{k: v for k, v in optional.items() if v is not None}
        }

        parser = partial(
            parse_csv_to_term_map,
            file_path=file_path,
            **parser_kwargs
        )
        return cls._build(parser, source_lang, target_lang, **kwargs)

    @classmethod
    def from_json(cls, input_json, source_lang, target_lang, schema, encoding = None, **kwargs):
        '''
        input_json can be either a path to a file or a dict / list

        Provide a json schema like this:
        schema = {
            "root": "data.items",
            "source": "translations.sourceTerms",
            "target": "translations.targetTerms"
        }
        '''
        args = {"encoding": encoding} if encoding else {}
        parser = partial(
            parse_json_to_term_map,
            input_json=input_json,
            schema=schema,
            **args
        )

        return cls._build(
            parser,
            source_lang,
            target_lang,
            **kwargs
        )

    def find_terms(self, source_text: str) -> list[SourceMatch]:
        return find_matches(self.automaton, source_text, self.source_lemmatizer)
