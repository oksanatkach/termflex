import argparse
import json
import sys
from functools import partial
from pathlib import Path

from termflex import Checker, Glossary

from .io.io import (FORMAT_SUFFIXES, collect_files, format_of, print_report,
                    process_many, save_json, summarize)


def make_checker(tbx: str, src: str, tgt: str) -> Checker:
    # Module-level on purpose: each worker process calls this (via a partial)
    # to build its own Checker, so nothing heavy has to be pickled.
    glossary = Glossary.from_tbx(file_path=tbx, source_lang=src, target_lang=tgt)
    return Checker(glossary=glossary)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="termflex",
        description="Check translated files (.po, .xlf/.xliff, .csv, .json) against a TBX glossary.\nThe glossary and --src/--tgt apply to every file under the input path.",
    )
    p.add_argument("input", help="file or directory (searched recursively)")
    p.add_argument("--format", action="append", choices=sorted(FORMAT_SUFFIXES), dest="formats",
                   help="file format to collect when INPUT is a directory (required for "
                        "directories; repeat for several). Ignored files of other formats.")
    p.add_argument("--tbx", required=True, help="glossary file")
    p.add_argument("--src", required=True, help="source language code, e.g. en")
    p.add_argument("--tgt", required=True, help="target language code, e.g. fr")
    p.add_argument("--source-field", help="source column (.csv) or key (.json); required for those formats")
    p.add_argument("--target-field", help="target column (.csv) or key (.json); required for those formats")
    p.add_argument("--context-field", help="optional context column/key (.csv, .json)")
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

    results, errors = process_many(
        args.input,
        checker_factory=partial(make_checker, args.tbx, args.src, args.tgt),
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
