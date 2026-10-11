import pytest
from termflex.utils.lang import parse_lang, InvalidLanguageError


@pytest.mark.parametrize("raw,tag", [
    ("uk", "uk"), ("UK", "uk"), (" uk ", "uk"),
    ("uk-UA", "uk"), ("uk_UA", "uk"), ("uk_ua", "uk"), ("uk_UA.UTF-8", "uk"),
    ("ukr", "uk"), ("eng", "en"), ("deu", "de"), ("ger", "de"),   # 639-3 and 639-2/B
    ("zh-hant-tw", "zh"), ("sr_Latn_RS", "sr"), ("es-419", "es"),
    ("ceb", "ceb"),                                               # no 639-1 code: keep 3-letter
    ("iw", "he"), ("in", "id"),                                   # deprecated aliases
])

def test_normalize(raw, tag):
    assert parse_lang(raw).language == tag


@pytest.mark.parametrize("bad", ["", "  ", "xx", "english", "u", "uk-", "uk-UA-UA", "uk-1", None, 5])
def test_invalid(bad):
    with pytest.raises(InvalidLanguageError):
        parse_lang(bad)
