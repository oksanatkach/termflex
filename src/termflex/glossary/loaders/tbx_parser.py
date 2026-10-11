from lxml import etree
from collections import defaultdict
import logging

from termflex.utils.lang import parse_lang

logger = logging.getLogger(__name__)


def extract_terms(lang_block):
    terms = []

    for t in lang_block.xpath(".//*[local-name()='term']"):
        if t.text and t.text.strip():
            terms.append(t.text.strip())

    return terms


def parse_tbx_to_term_map(path, source_lang: str, target_lang: str):
    tree = etree.parse(path)
    root = tree.getroot()

    # source_term -> list of target terms
    target_map = defaultdict(list)

    entries = root.xpath(
        ".//*[local-name()='conceptEntry' or local-name()='termEntry']"
    )

    for entry in entries:
        terms_per_lang = {}

        lang_blocks = entry.xpath(
            ".//*[local-name()='langSec' or local-name()='langSet']"
        )

        for lb in lang_blocks:
            lang_str = lb.get("{http://www.w3.org/XML/1998/namespace}lang")
            if not lang_str:
                logger.debug("Skipping language block: %s, lang not defined", lb)
                continue
            lang = parse_lang(lang_str)
            if not lang.language:
                logger.debug("Skipping language block: %s, can't parse lang %s", lb, lang_str)
                continue
            lang = lang.language

            if lang in [source_lang, target_lang]:
                terms = extract_terms(lb)

                if terms:
                    terms_per_lang[lang] = terms

        # skip incomplete concepts
        if source_lang not in terms_per_lang or target_lang not in terms_per_lang:
            logger.debug("Term %s doesn't have both source and target language terms", entry)
            continue

        # can't do target_map | terms_per_lang, some terms may be repeated across concepts (entries), we want to merge them instead
        for src_term in terms_per_lang[source_lang]:
            target_map[src_term].extend(terms_per_lang[target_lang])

    return target_map
