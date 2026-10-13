from __future__ import annotations

import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from pprint import pformat
from typing import Callable, Iterator
from dataclasses import asdict, is_dataclass
import warnings

from termflex import Checker, RenderedTermMatch

from .input_loaders.csv_input_parser import load_csv_units
from .input_loaders.json_input_parser import load_json_units
from .input_loaders.po_input_parser import load_po_units
from .input_loaders.xliff_input_parser import load_xliff_units

# Formats are chosen explicitly by the user for directory input: .csv/.json can't be told
# apart from unrelated files by extension, and a project may hold both translated .po files
# and untranslated .xlf files side by side, so nothing is collected by default.
FORMAT_SUFFIXES = {
    "po": {".po"},
    "xliff": {".xlf", ".xliff"},
    "csv": {".csv"},
    "json": {".json"},
}
SUPPORTED_SUFFIXES = set().union(*FORMAT_SUFFIXES.values())

# Per-worker state, set once by the pool initializer instead of being
# pickled and shipped with every file.
_checker: Checker | None = None


def _init_worker(checker_factory: Callable[[], Checker]) -> None:
    global _checker
    _checker = checker_factory()


def load_units(path: Path, field_options: dict | None = None) -> Iterator[dict]:
    """Pick the parser from the file extension."""
    suffix = Path(path).suffix.lower()

    if suffix == ".po":
        return load_po_units(path)

    if suffix in (".xlf", ".xliff"):
        return load_xliff_units(path)

    if suffix in (".csv", ".json"):
        if not field_options or "source_col" not in field_options or "target_col" not in field_options:
            raise ValueError(
                f"{path}: {suffix} input needs field_options with 'source_col' and 'target_col'"
            )
        loader = load_csv_units if suffix == ".csv" else load_json_units
        return loader(path, **field_options)

    raise ValueError(f"{path}: unsupported file format {suffix!r}")


def check_file(path: Path, checker: Checker | None = None,
               field_options: dict | None = None, render: bool = False) -> list[dict]:
    checker = checker or _checker
    results = []

    for unit in load_units(path, field_options):
        if not unit["target"]:
            continue

        matches = checker.check(source_text=unit["source"], target_text=unit["target"], render=render)
        failed = [m for m in matches if not m.match]
        succeeded = [m for m in matches if m.match]

        if matches:
            results.append({
                "file": str(path),
                "line": unit["lineno"],
                "plural_index": unit["plural_index"],
                "context": unit["context"],
                "source": unit["source"],
                "target": unit["target"],
                # plain dicts so the result is picklable and JSON-serializable
                "failed": failed,
                "succeeded": succeeded,
            })

    return results


def _safe_check_file(path: Path, render, field_options) -> tuple[Path, list[dict], str | None]:
    # One broken file must not kill the whole run.
    try:
        return path, check_file(path=path, render=render, field_options=field_options), None
    except Exception as e:  # noqa: BLE001
        return path, [], f"{type(e).__name__}: {e}"


def format_of(path) -> str | None:
    """'po' | 'xliff' | 'csv' | 'json' from the file suffix, or None if unsupported."""
    suffix = Path(path).suffix.lower()
    for name, suffixes in FORMAT_SUFFIXES.items():
        if suffix in suffixes:
            return name
    return None


def collect_files(path, formats=None) -> list[Path]:
    """A file path is returned as is. A directory needs `formats` (names from FORMAT_SUFFIXES):
    only files of those formats are collected, recursively, and anything else is ignored."""
    path = Path(path)
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise FileNotFoundError(f"input not found: {path}")

    choices = ", ".join(sorted(FORMAT_SUFFIXES))
    if not formats:
        raise ValueError(f"{path} is a directory: say which formats to collect ({choices})")
    unknown = sorted(set(formats) - set(FORMAT_SUFFIXES))
    if unknown:
        raise ValueError(f"unknown format(s) {unknown}; choose from: {choices}")

    suffixes = set().union(*(FORMAT_SUFFIXES[f] for f in formats))
    return sorted(p for p in path.rglob("*")
                  if p.is_file() and p.suffix.lower() in suffixes)


def process_many(path, checker_factory: Callable[[], Checker],
                 field_options: dict | None = None, max_workers: int | None = None,
                 formats=None, render: bool = False) -> list[dict]:
    """checker_factory must be a module-level function (or functools.partial of one)
    so it can be pickled on spawn platforms (macOS/Windows).

    formats: required when `path` is a directory, e.g. ["po", "xliff"].

    field_options example: {"source_col": "English", "target_col": "French"}
    (column names for .csv, object keys for .json)
    """
    files = collect_files(path, formats)
    all_results: list[dict] = []
    errors: dict[str, str] = {}

    if max_workers == 1:  # easy debugging, no subprocesses
        _init_worker(checker_factory)
        outcomes = (_safe_check_file(f, render, field_options) for f in files)
    else:
        ex = ProcessPoolExecutor(max_workers=max_workers,
                                 initializer=_init_worker,
                                 initargs=(checker_factory,))
        futures = [ex.submit(_safe_check_file, f, render, field_options) for f in files]
        outcomes = (f.result() for f in as_completed(futures))

    try:
        for f, results, err in outcomes:
            if err:
                errors[str(f)] = err
            all_results.extend(results)
    finally:
        if max_workers != 1:
            ex.shutdown()

    all_results.sort(key=lambda r: (r["file"], r["line"], r["plural_index"] or 0))
    return all_results, errors


def print_report(results: list[dict], show_ok: bool=True) -> None:
    """Print the segments with missing terms; with show_ok, also the correct matches."""
    matches = [m for r in results for m in r["failed"] + r["succeeded"]]
    if matches and not any(isinstance(m, RenderedTermMatch) for m in matches):
        warnings.warn(
            "Results are not rendered; run checker.check(..., render=True) "
            "to see the terms marked in the text.",
            stacklevel=2,
        )

    current = None
    for r in results:
        shown = r["failed"] + (r["succeeded"] if show_ok else [])
        if not shown:
            continue                      # nothing to show: skip the segment's headers too

        if r["file"] != current:
            current = r["file"]
            print(f"\n=== {current}")
        form = f" (msgstr[{r['plural_index']}])" if r["plural_index"] is not None else ""
        print(f"\n  line {r['line']}{form}")
        if r["context"]:
            print(f"  CTX: {r['context']}")

        for m in shown:
            status = m.match_type.upper() if m.match else "MISSING"
            print(m)
            print(f"    [{status}] {m.source_term!r} -> {m.found_targets or m.expected_targets}")
            if isinstance(m, RenderedTermMatch):
                if m.source_rendered:
                    print(f"      SRC: {m.source_rendered}")
                    print(f"      TGT: {m.target_rendered}")
                print(f"      SRC lemmas: {m.source_lemmas_rendered}")
                print(f"      TGT lemmas: {m.target_lemmas_rendered}")
            else:
                print(f"      SRC: {r['source']}")
                print(f"      TGT: {r['target']}")


def save_json(results: list[dict], path, encoding="utf-8") -> None:
    def to_json(obj):
        if is_dataclass(obj):
            return asdict(obj)
        raise TypeError(f"{type(obj).__name__} is not JSON serializable")

    with open(path, "w", encoding=encoding) as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=to_json)


def summarize(results: list[dict], errors: dict[str, str] | None = None) -> dict:
    by_term = Counter(i.source_term for r in results for i in r["failed"])
    succeeded_count = sum(len(r["succeeded"]) for r in results)
    failed_count = sum(by_term.values())

    return {
        "accuracy":  1.0 if not failed_count else failed_count / (succeeded_count + failed_count),
        "total_issues": failed_count,
        "total_string_pairs": len(results),
        "total_files": len({r["file"] for r in results}),
        "top_missing_terms": by_term.most_common(10),
        "files_failed_to_parse": errors or {},
    }
