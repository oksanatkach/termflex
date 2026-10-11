import polib
from collections import defaultdict


def parse_po_to_term_map(file_path):
    po = polib.pofile(file_path)

    target_map = defaultdict(list)

    for entry in po:
        src = entry.msgid.strip()

        if entry.msgstr:
            tgt = entry.msgstr.strip()
            target_map[src].append(tgt)

        if entry.msgstr_plural:
            for v in entry.msgstr_plural.values():
                target_map[src].append(v.strip())

    return target_map
