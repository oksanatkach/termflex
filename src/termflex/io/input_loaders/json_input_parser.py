import json


def load_json_units(
    path,
    source_col,
    target_col,
    context_col=None,
    encoding="utf-8-sig",
):
    """Yield the same unit dicts as load_po_units / load_csv_units.

    Expects a JSON list of objects, e.g.
        [{"en": "Send it to my e-mail", "fr": "Envoyez-le à mon courriel"}, ...]
    source_col / target_col / context_col are the object keys (the parameter
    names match load_csv_units so the CLI can pass the same options to both).

    "lineno" is the 1-based position of the record in the list, because JSON
    has no meaningful line numbers.
    """
    with open(path, encoding=encoding) as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a JSON list of objects at the top level")

    for idx, rec in enumerate(data, start=1):
        if not isinstance(rec, dict):
            raise ValueError(f"{path}: record {idx} is not an object")

    missing = [k for k in (source_col, target_col, context_col)
               if k is not None and not any(k in rec for rec in data)]
    if missing:
        keys = sorted({k for rec in data for k in rec})
        raise ValueError(f"{path}: key(s) {missing} not found; available keys: {keys}")

    for idx, rec in enumerate(data, start=1):
        source, target = rec.get(source_col), rec.get(target_col)

        for name, value in ((source_col, source), (target_col, target)):
            if value is not None and not isinstance(value, str):
                raise ValueError(
                    f"{path}: record {idx}: {name!r} must be a string, "
                    f"got {type(value).__name__}"
                )

        yield {
            "source": source or "",
            "target": target or "",
            "context": (rec.get(context_col) or None) if context_col else None,
            "plural_index": None,
            "lineno": idx,
        }
