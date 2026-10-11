try:
    from lxml import etree as ET
    _LXML = True
except ImportError:  # stdlib fallback: works, but no real line numbers
    import xml.etree.ElementTree as ET
    _LXML = False

# Inline elements whose content is code (placeholders, tags), not translatable text.
_CODE_TAGS = {"ph", "bpt", "ept", "it"}


def _local(tag) -> str:
    # strips the namespace; comments / processing instructions have non-str tags
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def _text(el) -> str:
    """Plain text of a <source>/<target>, dropping inline code content."""
    parts = [el.text or ""]
    for child in el:
        if _local(child.tag) not in _CODE_TAGS:
            parts.append(_text(child))
        parts.append(child.tail or "")
    return "".join(parts)


def _child(el, name):
    for c in el:
        if _local(c.tag) == name:
            return c
    return None


def _parse(path):
    if _LXML:
        parser = ET.XMLParser(resolve_entities=False, no_network=True)
        return ET.parse(str(path), parser).getroot()
    return ET.parse(str(path)).getroot()


def load_xliff_units(path):
    """Yield the same unit dicts as load_po_units / load_csv_units / load_json_units.

    Supports XLIFF 1.2 (<trans-unit>) and 2.x (<unit>/<segment>).
    - Inline code content (<ph>, <bpt>, <ept>, <it>) is dropped; text inside
      formatting tags like <g>, <mrk>, <pc> is kept.
    - Units with translate="no" are skipped.
    - "context" is the unit's resname (1.2) or name (2.x), if present.
    - "lineno" is the source line of the unit/segment when lxml is installed;
      otherwise it falls back to the 1-based position of the unit (1.2) or segment (2.x).
    """
    root = _parse(path)
    counter = 0

    def make(node, unit, source_el, target_el):
        nonlocal counter
        context = unit.get("resname") or unit.get("name") or None
        line = getattr(node, "sourceline", None) if _LXML else None
        return {
            "source": _text(source_el).strip(),
            "target": _text(target_el).strip() if target_el is not None else "",
            "context": context,
            "plural_index": None,
            "lineno": line or counter,
        }

    for el in root.iter():
        name = _local(el.tag)

        if name == "trans-unit":  # XLIFF 1.2
            counter += 1
            if el.get("translate") == "no":
                continue
            source_el = _child(el, "source")
            if source_el is None:
                continue
            yield make(el, el, source_el, _child(el, "target"))

        elif name == "unit":  # XLIFF 2.x
            if el.get("translate") == "no":
                continue
            for seg in el:
                if _local(seg.tag) != "segment":  # skips <ignorable>, <notes>, ...
                    continue
                counter += 1
                source_el = _child(seg, "source")
                if source_el is None:
                    continue
                yield make(seg, el, source_el, _child(seg, "target"))
