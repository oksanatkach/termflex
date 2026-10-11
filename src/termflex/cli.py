import argparse
import json
import sys
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

from termflex import Checker, Glossary

from .io.io import (FORMAT_SUFFIXES, collect_files, format_of, print_report,
                    process_many, save_json, summarize)
from .lemmatizers.morph_backends import available_backends, resolve_backend_spec


# suffix -> Glossary constructor. All of them take the glossary path as their first argument;
# the format-specific extras (CSV columns, JSON schema) are passed as keywords.
GLOSSARY_LOADERS = {
    ".tbx": Glossary.from_tbx,
    ".po": Glossary.from_po,
    ".csv": Glossary.from_csv,
    ".json": Glossary.from_json,
}


@dataclass(frozen=True)
class GlossarySpec:
    """Everything needed to load the glossary. Plain data (the suffix, not the loader
    function), so it pickles into worker processes."""
    path: str
    suffix: str                              # key into GLOSSARY_LOADERS, e.g. ".csv"
    extra: dict = field(default_factory=dict)   # csv: column names; json: schema


def load_glossary(spec: GlossarySpec, src: str, tgt: str, **kwargs) -> Glossary:
    loader = GLOSSARY_LOADERS[spec.suffix]
    return loader(spec.path, source_lang=src, target_lang=tgt, **spec.extra, **kwargs)


def make_checker(glossary: GlossarySpec, src: str, tgt: str,
                 source_lemmatizer: str | None = None,
                 target_lemmatizer: str | None = None) -> Checker:
    # Module-level on purpose: each worker process calls this (via a partial)
    # to build its own Checker, so nothing heavy has to be pickled. The lemmatizer
    # arguments are plain strings; they are resolved here, inside each worker, so a
    # "module:name" backend is imported (and registered) in every process.
    kwargs = {}
    if source_lemmatizer:
        kwargs["source_lemmatizer"] = resolve_backend_spec(source_lemmatizer)
    if target_lemmatizer:
        kwargs["target_lemmatizer"] = resolve_backend_spec(target_lemmatizer)
    return Checker(glossary=load_glossary(glossary, src, tgt, **kwargs))


def glossary_spec_from_args(parser: argparse.ArgumentParser, args) -> GlossarySpec:
    """Validate the glossary options up front, so mistakes fail before any worker starts."""
    path = Path(args.glossary)
    if not path.is_file():
        parser.error(f"glossary not found: {args.glossary}")

    suffix = f".{args.glossary_format}" if args.glossary_format else path.suffix.lower()
    if suffix not in GLOSSARY_LOADERS:
        parser.error(f"cannot tell the glossary format of {path.name}: pass --glossary-format "
                     f"({', '.join(_glossary_formats())})")

    extra = {}
    if suffix == ".csv":
        if not (args.glossary_source_field and args.glossary_target_field):
            parser.error("a CSV glossary needs --glossary-source-field and --glossary-target-field")
        extra = {"source_term_column": args.glossary_source_field,
                 "target_term_column": args.glossary_target_field}
    elif suffix == ".json":
        if not args.glossary_schema:
            parser.error("a JSON glossary needs --glossary-schema FILE "
                         '(e.g. {"root": "data.items", "pairs": {"source": "...", "target": "..."}})')
        try:
            extra = {"schema": json.loads(Path(args.glossary_schema).read_text(encoding="utf-8"))}
        except (OSError, ValueError) as e:
            parser.error(f"--glossary-schema: {e}")

    return GlossarySpec(str(path), suffix, extra)


def _glossary_formats() -> list[str]:
    return sorted(suffix.lstrip(".") for suffix in GLOSSARY_LOADERS)


class _ListBackends(argparse.Action):
    """--list-backends: print the registered backends and exit (like --version)."""

    def __init__(self, option_strings, dest, **kwargs):
        super().__init__(option_strings, dest, nargs=0, default=argparse.SUPPRESS, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        for name, langs in available_backends().items():
            print(f"{name}: {', '.join(langs) if langs else 'any language / unknown'}")
        print("auto: let termflex choose")
        parser.exit()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="termflex",
        description="Check translated files (.po, .xlf/.xliff, .csv, .json) against a glossary (TBX, PO, CSV or JSON).\nThe glossary and --src/--tgt apply to every file under the input path.",
    )
    p.add_argument("input", help="file or directory (searched recursively)")
    p.add_argument("--format", action="append", choices=sorted(FORMAT_SUFFIXES), dest="formats",
                   help="file format to collect when INPUT is a directory (required for "
                        "directories; repeat for several). Ignored files of other formats.")
    p.add_argument("--glossary", "--tbx", dest="glossary", required=True, metavar="FILE",
                   help="glossary file (.tbx, .po, .csv, .json; format inferred from the extension). "
                        "--tbx is accepted as an alias")
    p.add_argument("--glossary-format", choices=_glossary_formats(),
                   help="glossary format, if the extension does not say it")
    p.add_argument("--glossary-source-field", metavar="COLUMN", help="CSV glossary: source term column")
    p.add_argument("--glossary-target-field", metavar="COLUMN", help="CSV glossary: target term column")
    p.add_argument("--glossary-schema", metavar="FILE",
                   help="JSON glossary: a JSON file with the schema (root + pairs.source/pairs.target)")
    p.add_argument("--src", required=True, help="source language code, e.g. en")
    p.add_argument("--tgt", required=True, help="target language code, e.g. fr")
    p.add_argument("--source-field", help="source column (.csv) or key (.json); required for those formats")
    p.add_argument("--target-field", help="target column (.csv) or key (.json); required for those formats")
    p.add_argument("--context-field", help="optional context column/key (.csv, .json)")
    spec_help = ('"auto", the name of a registered backend (see --list-backends), '
                 'or a "module:name" path to your own Backend class or function')
    p.add_argument("--lemmatizer", metavar="SPEC",
                   help=f"lemmatizer for both languages: {spec_help}")
    p.add_argument("--source-lemmatizer", metavar="SPEC",
                   help="lemmatizer for the source language only (overrides --lemmatizer)")
    p.add_argument("--target-lemmatizer", metavar="SPEC",
                   help="lemmatizer for the target language only (overrides --lemmatizer)")
    p.add_argument("--list-backends", action=_ListBackends,
                   help="show the available lemmatizer backends and exit")
    p.add_argument("--json", metavar="FILE", help="also write the full results to a JSON file")
    p.add_argument("--workers", type=int, default=None,
                   help="worker processes (default: CPU count; 1 = no subprocesses)")
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    if not input_path.exists():
        parser.error(f"input not found: {args.input}")

    formats = args.formats
    if input_path.is_dir():
        if not formats:
            parser.error("INPUT is a directory: choose what to check with --format "
                         f"({', '.join(sorted(FORMAT_SUFFIXES))}); repeat it for several formats")
    else:
        inferred = format_of(input_path)
        if inferred is None:
            parser.error(f"unsupported file type: {input_path.suffix or input_path.name}")
        if formats and inferred not in formats:
            parser.error(f"{input_path.name} is a {inferred} file but --format says {formats}")
        formats = [inferred]

    files = collect_files(input_path, formats)
    if not files:
        parser.error(f"no {'/'.join(formats)} files found in {args.input}")

    field_options = None
    if {"csv", "json"} & set(formats):
        if not (args.source_field and args.target_field):
            parser.error("CSV/JSON input requires --source-field and --target-field")
        field_options = {"source_col": args.source_field,
                         "target_col": args.target_field,
                         "context_col": args.context_field}

    glossary_spec = glossary_spec_from_args(parser, args)

    source_spec = args.source_lemmatizer or args.lemmatizer
    target_spec = args.target_lemmatizer or args.lemmatizer
    for flag, spec in (("--source-lemmatizer" if args.source_lemmatizer else "--lemmatizer", source_spec),
                       ("--target-lemmatizer" if args.target_lemmatizer else "--lemmatizer", target_spec)):
        if spec:                        # fail fast, before any worker process starts
            try:
                resolve_backend_spec(spec)
            except Exception as e:      # unknown name, import error, bad path, ...
                parser.error(f"{flag}: {e}")

    results, errors = process_many(
        args.input,
        checker_factory=partial(make_checker, glossary_spec, args.src, args.tgt, source_spec, target_spec),
        field_options=field_options,
        max_workers=args.workers,
        formats=formats,
    )

    print_report(results)

    for path, err in errors.items():
        print(f"ERROR {path}: {err}", file=sys.stderr)

    summary = summarize(results, errors)
    print("\n--- summary ---")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.json:
        save_json(results, args.json)

    # exit codes for CI use: 0 = clean, 1 = term issues found, 2 = some files failed
    if errors:
        return 2
    return 1 if results else 0


if __name__ == "__main__":
    sys.exit(main())
