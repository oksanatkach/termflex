import polib


def load_po_units(path, skip_fuzzy=True):
    po = polib.pofile(str(path))

    for entry in po:
        if entry.obsolete:
            continue

        # fuzzy translations are unreviewed guesses, so they produce noisy QA reports
        if skip_fuzzy and "fuzzy" in entry.flags:
            continue

        if entry.msgid_plural:
            forms = sorted(entry.msgstr_plural.items())

            for i, msgstr in forms:
                if len(forms) == 1:
                    # one-form languages (ja, zh, ...): the single msgstr covers
                    # both the singular and the plural source
                    source = f"{entry.msgid}\n{entry.msgid_plural}"
                else:
                    # msgstr[0] translates msgid, every other form translates msgid_plural
                    source = entry.msgid if i == 0 else entry.msgid_plural

                yield {
                    "source": source,
                    "target": msgstr,
                    "context": entry.msgctxt,
                    "plural_index": i,
                    "lineno": entry.linenum,
                }
        else:
            yield {
                "source": entry.msgid,
                "target": entry.msgstr,
                "context": entry.msgctxt,
                "plural_index": None,
                "lineno": entry.linenum,
            }
