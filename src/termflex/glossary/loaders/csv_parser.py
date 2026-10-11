import csv
from collections import defaultdict


def parse_csv_to_term_map(
    file_path,
    source_col,
    target_col,
    delimiter=",",
    newline="",
    encoding="utf-8"
):
    target_map = defaultdict(list)

    with open(file_path, newline=newline, encoding=encoding) as f:
        reader = csv.DictReader(f, delimiter=delimiter)

        for row in reader:
            src = row.get(source_col)
            tgt = row.get(target_col)

            if not src or not tgt:
                continue

            src = src.strip()
            tgt = tgt.strip()

            if not src or not tgt:
                continue

            target_map[src].append(tgt)

    return target_map
