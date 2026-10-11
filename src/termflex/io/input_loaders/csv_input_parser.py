import csv


def _detect_delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def load_csv_units(
    path,
    source_col,
    target_col,
    context_col=None,
    delimiter=None,
    encoding="utf-8-sig",  # utf-8-sig also handles the BOM that Excel adds
):
    """Yield the same unit dicts as load_po_units.

    "lineno" is the 1-based CSV row number, with the header as row 1,
    so it matches the row number you see in Excel / LibreOffice.
    """
    with open(path, newline="", encoding=encoding) as f:
        if delimiter is None:
            delimiter = _detect_delimiter(f.read(4096))
            f.seek(0)

        reader = csv.DictReader(f, delimiter=delimiter)

        missing = [c for c in (source_col, target_col, context_col)
                   if c is not None and c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(
                f"{path}: column(s) {missing} not found; "
                f"available columns: {reader.fieldnames}"
            )

        for rowno, row in enumerate(reader, start=2):
            yield {
                "source": row[source_col] or "",
                "target": row[target_col] or "",  # short rows give None
                "context": (row[context_col] or None) if context_col else None,
                "plural_index": None,
                "lineno": rowno,
            }
