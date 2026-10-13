"""Stand-in checker so the io layer can be tested without the lemmatizer models.

Module-level on purpose: ProcessPoolExecutor has to pickle the factory.
"""
from termflex.checker import RenderedTermMatch, TermMatch

TERM, TARGET = "e-mail", "courriel"


class FakeChecker:
    """Flags 'e-mail' as missing unless the target contains 'courriel'."""

    def __init__(self, burn=0):
        self.burn = burn  # pointless CPU work, to make benchmarks measurable

    def check(self, source_text, target_text, render=False):
        x = 0
        for i in range(self.burn):
            x += i * i
        if TERM not in source_text:
            return []

        found = TARGET in target_text
        base = TermMatch(
            source_term=TERM,
            expected_targets=[TARGET],
            found_targets=[TARGET] if found else [],
            match=found,
            match_type="exact" if found else "missing",
            source_span=None,
            target_span=None,
            source_lemma_span=None,
            target_lemma_span=None,
            source_lemmas=source_text.split(),
            target_lemmas=target_text.split() if found else None,
        )
        if not render:
            return [base]
        return [RenderedTermMatch(
            **base.__dict__,
            source_rendered=source_text.replace(TERM, f"<term>{TERM}</term>", 1),
            target_rendered=target_text.replace(TARGET, f"<term>{TARGET}</term>", 1),
            source_lemmas_rendered=" ".join(base.source_lemmas),
            target_lemmas_rendered=" ".join(target_text.split()),
        )]


def make_fake_checker():
    return FakeChecker()


def make_slow_fake_checker(burn=20_000):
    return FakeChecker(burn)
