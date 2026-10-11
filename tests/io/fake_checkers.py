"""Stand-in checker so the io layer can be tested without the lemmatizer models.

Module-level on purpose: ProcessPoolExecutor has to pickle the factory.
"""
from collections import namedtuple

Match = namedtuple("Match", "match source_term expected_targets")


class FakeChecker:
    """Flags 'e-mail' as missing unless the target contains 'courriel'."""

    def __init__(self, burn=0):
        self.burn = burn  # pointless CPU work, to make benchmarks measurable

    def check(self, source_text, target_text):
        x = 0
        for i in range(self.burn):
            x += i * i
        if "e-mail" not in source_text:
            return []
        return [Match("courriel" in target_text, "e-mail", ["courriel"])]


def make_fake_checker():
    return FakeChecker()


def make_slow_fake_checker(burn=20_000):
    return FakeChecker(burn)
