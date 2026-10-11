import re


def default_normalize(text: str) -> str:
    text = text.lower()
    text = text.replace("-", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def find_subphrase(text: str, phrase: str):
    """Inclusive (start, end) of `phrase` as a whole-word match in `text`, or None."""
    m = re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text)
    return (m.start(), m.end() - 1) if m else None


def find_seq(seq, sub):
    """Index where `sub` occurs contiguously in `seq`, or None."""
    seq, sub = tuple(seq), tuple(sub)
    n = len(sub)
    if n == 0:
        return None
    return next((i for i in range(len(seq) - n + 1) if seq[i:i + n] == sub), None)
