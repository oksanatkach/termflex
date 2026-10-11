# Termflex: Morphology-Aware Term QA

Use termflex to:

- QA translations in .po, .xlf / .xliff, .csv and .json files against a glossary (in standard TBX and PO formats or free form CSV or JSON).
- Ground LLM output by checking that generated text uses the approved terminology. In this case, the source and target languages are the same, the source string is the prompt, and the target string is the LLM response.

**Task:** In localization / machine translation / technical writing / LLM generation, the resulting text can often be semantically correct but can ignore pre-defined required terminology and use synonyms instead. This is an issue for consistency across documents and previously agreed upon project language style.

**Problem:** Terminology QA checks if the resulting text contains the desirable terms pre-defined in a project glossary. However, term checkers are often naive and only do direct string matching, ignoring different word forms. This produces many false positives and false negatives.

**Solution:** Termflex performs term QA even when the generated term is an inflected form by using smart lemma matching instead of plain string matching. Plain string matching flags correct translations as errors whenever a language inflects its words: Ukrainian пошту or пошті when the glossary says пошта, French courriels when the glossary says courriel. Termflex lemmatizes both sides, so it matches on the dictionary form and still reports exactly where the term was found.

## Install

```bash
pip install termflex
```

Optional morphology backends are installed as extras:

```bash
pip install "termflex[pymorphy3]"          # Ukrainian dictionaries
pip install "termflex[pymorphy3-ruzzian]"  # Russian dictionaries
pip install "termflex[all]"                # everything
```

`simplemma` is installed by default. Requires Python 3.10 or newer.

## Quick start (CLI)

Check one file:

```bash
termflex translations/uk.po --glossary glossary.tbx --src en --tgt uk
```

Check a directory. Directories need `--format`, so that nothing is checked by accident:

```bash
termflex locale/uk --format po --glossary glossary.tbx --src en --tgt uk
termflex project/ --format po --format xliff --glossary glossary.tbx --src en --tgt uk
```

CSV and JSON files have no fixed structure, so name the source and target fields:

```bash
termflex pairs.csv --glossary glossary.tbx --src en --tgt fr \
    --source-field English --target-field French
termflex data/ --format json --glossary glossary.tbx --src en --tgt fr \
    --source-field en --target-field fr
```

### Options

| Option | Meaning |
| --- | --- |
| `input` | A file, or a directory (searched recursively). |
| `--format {po,xliff,csv,json}` | Which files to collect from a directory. Required for directories, repeatable. For a single file the format is inferred from its extension. |
| `--glossary FILE` | The glossary: `.tbx`, `.po`, `.csv` or `.json`, with the format inferred from the extension. `--tbx` still works as an alias. |
| `--glossary-format {tbx,po,csv,json}` | Set the glossary format when the extension does not say it. |
| `--glossary-source-field`, `--glossary-target-field` | CSV glossary: the columns holding the source and target terms. Required for CSV glossaries. |
| `--glossary-schema FILE` | JSON glossary: a JSON file describing where the terms are, e.g. `{"root": "data.items", "pairs": {"source": "...", "target": "..."}}`. Required for JSON glossaries. |
| `--src`, `--tgt` | Source and target language codes. They apply to every file checked in the run. |
| `--source-field`, `--target-field` | Column (CSV) or key (JSON) holding the source and target text. Required for those formats. |
| `--context-field` | Optional column or key to show as context in the report. |
| `--lemmatizer SPEC` | Lemmatizer for both languages: `auto`, a registered backend name, or `module:name` (see [Choosing a backend](#choosing-a-backend-from-the-cli)). |
| `--source-lemmatizer SPEC`, `--target-lemmatizer SPEC` | Same, for one side only. They override `--lemmatizer`. |
| `--list-backends` | Print the available backends and exit. |
| `--json FILE` | Also write the full results to a JSON file. |
| `--workers N` | Worker processes (default: CPU count; `1` runs in-process, which is handy for debugging). |

Language selection is deliberately left to you. A glossary covers one language pair, so check one language per run, for example `locale/uk`, not the whole `locale/` tree.

### Choosing a backend from the CLI

Without a lemmatizer flag, the glossary's default is used. Otherwise a spec can be:

| Spec | Meaning |
| --- | --- |
| `auto` | Termflex's default choice (currently `simplemma`). |
| `pymorphy3`, `simplemma`, ... | The name of a registered backend (see `--list-backends`). Backends from installed plugins are included. |
| `my_module:my_function` | A function `fn(text, lang_code)`, imported from an installed module or the current directory. |
| `my_module:MyBackend` | A `Backend` subclass; it is registered under its `name` if it is not registered yet. |

```bash
termflex uk.po --glossary glossary.tbx --src en --tgt uk --target-lemmatizer pymorphy3
termflex uk.po --glossary glossary.tbx --src en --tgt uk --lemmatizer my_lemmas:lemmatize
```

Specs are validated before any file is read, so a typo fails immediately with a clear message. Each worker process resolves the spec on its own.

### Output and exit codes

Failures are printed grouped by file, with the source, the target and the glossary terms that are missing:

```
=== locale/uk/LC_MESSAGES/django.po

  line 120
  SRC: Send it to my e-mail
  TGT: Надішліть це мені
  MISSING: 'e-mail' -> expected one of ['електронна пошта']
```

The run ends with a summary (total issues, files with issues, most frequently missing terms, and files that could not be read). File-level errors go to stderr.

| Exit code | Meaning |
| --- | --- |
| `0` | Clean: no terminology issues. |
| `1` | Terminology issues were found. |
| `2` | Some files could not be read or parsed. |

These make it easy to use in CI.

## Supported input formats

| Format | Notes |
| --- | --- |
| `.po` | Plural forms are paired with the right source string. Fuzzy and obsolete entries are skipped. |
| `.xlf`, `.xliff` | XLIFF 1.2 and 2.x. Inline code (`<ph>`, `<bpt>`, `<ept>`, `<it>`) is dropped, units with `translate="no"` are skipped. |
| `.csv` | Delimiter is auto-detected; UTF-8 with or without a BOM. |
| `.json` | A list of objects, e.g. `[{"en": "...", "fr": "..."}]`. |

Units with an empty target are skipped.

## Python API

```python
from termflex import Glossary, Checker

glossary = Glossary.from_tbx(
    file_path="glossary.tbx",
    source_lang="en",
    target_lang="fr",
)
checker = Checker(glossary=glossary)

matches = checker.check(
    source_text="send it to my e-mail",
    target_text="envoyez-le à mon courriel",
    render=True,
)
for m in matches:
    print(m.source_term, m.match, m.match_type)
    print(m.target_rendered)   # the target text with the term wrapped in <term>...</term>
```

`check()` returns one result for each glossary term found in the source text. Each result tells you whether the expected translation was found and how:

| `match_type` | Meaning |
| --- | --- |
| `exact` | The expected form appears as written, and also matches by lemma. |
| `lemma` | An inflected form was found: the lemmas match, the surface text differs. |
| `surface` | The surface text matches, but no lemma match was found. |
| `missing` | None of the expected translations was found. |

Spans are available in two flavors. `source_span` and `target_span` are character offsets into the text, and `source_lemma_span` and `target_lemma_span` are token offsets into the lemma lists. All spans are inclusive on both ends.

`Glossary` from file builders also accept custom `normalize` and `tokenize` callables, which are then passed on to the lemmatizers.
By default, `normalize` comes from `termflex/utils/utils.py:default_normalize`, and `tokenize` comes from the lemmatizer backend.
When `tokenize` is custom, termflex is able to pass it on to the `Doc` class, which allows to align the lemmas with the tokens and highlight the identified term in the original text, not only in the lemmas. For this reason, if you provide a custom tokenizer, you will also get a valid string in `match.source_rendered`.

## Morphology backends

A backend turns text into lemmas. Termflex ships with `simplemma` (installed by default) and `pymorphy3` (optional extra), and you can pass your own callable. Backends are created with `get_backend` and cached, so asking for the same backend and language twice returns the same instance.

### Writing your own backend

**The quickest way: a function.** Pass any function `fn(text, lang_code) -> list[str]` (or a single `str`) to `get_backend`. It receives the text and the language code (`"uk"` for `uk_UA`) and returns the lemmas:

```python
from termflex.lemmatizers import get_backend

def my_lemmatizer(text: str, lang_code: str) -> list[str]:
    return [word.lower() for word in text.split()]

backend = get_backend(my_lemmatizer, "uk")
```
If you pass `tokenize=`, your function is called once per token instead of once per text.
Termflex normalizes the input before calling you and casefolds the lemmas you return. You can pass your own `normalize=` as well.

To make a function available by name, register it with the decorator:

```python
from termflex.lemmatizers import register_function

@register_function
def my_lemmatizer(text: str, lang_code: str) -> list[str]:
    ...

get_backend("my_lemmatizer", "uk")   # an instance of FunctionBackend[my_lemmatizer]
```

To pass the lemmatizer name and a list of supported languages use:
```python
@register_function("hunspell-r", languages={"uk"})
def my_lemmatizer(text: str, lang_code: str) -> list[str]:
    ...

get_backend("my_lemmatizer", "uk")   # an instance of FunctionBackend[hunspell-r]
```

**A reusable backend: a class.** Subclass `Backend`, implement `_lemmatize`, and register it with the decorator:

```python
from termflex.lemmatizers import Backend, register_backend

@register_backend
class MyBackend(Backend):
    name = "mybackend"
    languages = frozenset({"uk", "en"})   # base codes; None means any language

    def __init__(self, lang, normalize, tokenize=None):
        super().__init__(lang, normalize, tokenize)   # parses the language and validates it
        ...                                           # load your models here; self.lang_code is e.g. "uk"

    def _lemmatize(self, text: str) -> list[str]:
        ...                                           # lemmas for every token in `text`
```

See `termflex/lemmatizers/morph_backends.py` for the existing backends as a reference.

**Shipping a backend in a package.** Decorators only run when their module is imported. To have termflex import your module, list it as an entry point (one per module, pointing at the module, not at a class or function):
```toml
[project.entry-points."termflex.lemmatizers"]
mybackend = "my_package.backend:MyBackend"
```

This is needed if you want CLI to see your custom backend.
Backends must come from installed packages, because each worker process loads them on its own.

The module then registers its backends with `@register_backend` / `@register_function`. Plugins are loaded lazily, the first time a name is not found or backends are listed. A plugin that fails to import is skipped with a warning. Reinstall the package after changing its entry points.

Backends must come from installed packages (or modules importable by `module:name`), because each worker process loads them on its own.

By default, instances are shared per language (`uk` and `uk_UA` give the same instance). If your backend behaves differently per region or script, override `cache_key` so that those variants are cached separately:

```python
@register_backend
class SimplemmaRegionBackend(SimplemmaBackend):
    name = "simplemma-region"

    @classmethod
    def cache_key(cls, lang):
        return str(lang)
```

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[all,test]"
python -m pytest -q
```

Run pytest as a module (`python -m pytest`), because the process-pool tests need the repository root on the import path.

## License

MIT
