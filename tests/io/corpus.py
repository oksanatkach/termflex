"""Generates a synthetic corpus with a KNOWN number of failures (the oracle)."""
import csv
import json
from pathlib import Path

import polib

FIELD_OPTIONS = {"source_col": "en", "target_col": "fr"}
FORMATS = ("po", "csv", "json", "xlf")


def is_bad(i: int) -> bool:
    return i % 3 == 0


def expected_failures(units_per_file: int) -> int:
    return sum(is_bad(i) for i in range(units_per_file))


def _pairs(k, n):
    return [
        (f"Send it to my e-mail ({k}-{i})",
         f"Envoyez à mon {'adresse' if is_bad(i) else 'courriel'} ({k}-{i})")
        for i in range(n)
    ]


def _write_po(path, pairs):
    po = polib.POFile()
    po.metadata = {"Content-Type": "text/plain; charset=UTF-8"}
    for s, t in pairs:
        po.append(polib.POEntry(msgid=s, msgstr=t))
    po.save(str(path))


def _write_csv(path, pairs):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["en", "fr"])
        w.writerows(pairs)


def _write_json(path, pairs):
    path.write_text(json.dumps([{"en": s, "fr": t} for s, t in pairs], ensure_ascii=False),
                    encoding="utf-8")


def _write_xlf(path, pairs):
    units = "".join(
        f'<trans-unit id="{i}"><source>{s}</source><target>{t}</target></trans-unit>'
        for i, (s, t) in enumerate(pairs)
    )
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        f'<file source-language="en" target-language="fr" datatype="plaintext" original="x">'
        f'<body>{units}</body></file></xliff>',
        encoding="utf-8",
    )


_WRITERS = {"po": _write_po, "csv": _write_csv, "json": _write_json, "xlf": _write_xlf}


LAYOUTS = {
    "gettext": lambda k: Path(f"lang{k % 5}") / "LC_MESSAGES",        # locale/xx/LC_MESSAGES/
    "flat": lambda k: Path("."),                                      # everything in one folder
    "per_language": lambda k: Path(f"lang{k % 5}"),                   # xx/file
    "deep": lambda k: Path("src", "app", "i18n", f"v{k % 2}", f"lang{k % 5}"),
    "android_like": lambda k: Path(f"res/values-{k % 5}"),
}


def write_corpus(root, n_files, units_per_file, layout="gettext"):
    """Spread files over formats and a directory layout (default: locale/<lang>/LC_MESSAGES/)."""
    root = Path(root)
    paths = []
    for k in range(n_files):
        fmt = FORMATS[k % len(FORMATS)]
        d = root / LAYOUTS[layout](k)
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"file{k}.{fmt}"
        _WRITERS[fmt](p, _pairs(k, units_per_file))
        paths.append(p)
    return paths
