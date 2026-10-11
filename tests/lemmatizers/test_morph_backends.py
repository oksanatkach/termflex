import pytest
from termflex.lemmatizers.morph_backends import (UnsupportedLanguageError, available_backends, backends_for,
                                                 get_backend)
from termflex.utils.lang import InvalidLanguageError


def test_region_and_iso3_spellings_match():
    for code in ["uk", "uk_UA", "ukr", "UK-ua"]:
        assert get_backend("pymorphy3", code).lang_code == "uk"


def test_pymorphy_rejects_english_with_helpful_message():
    with pytest.raises(UnsupportedLanguageError) as e:
        get_backend("pymorphy3", "en")
    msg = str(e.value)
    assert "ru, uk" in msg and "simplemma" in msg


def test_invalid_code():
    with pytest.raises(InvalidLanguageError):
        get_backend("pymorphy3", "xx")


def test_unknown_backend():
    with pytest.raises(ValueError, match="Available"):
        get_backend("nope", "uk")


def test_instances_are_shared():
    assert get_backend("pymorphy3", "uk") is get_backend("pymorphy3", "uk_UA")


def test_different_languages_are_not_shared():
    assert get_backend("pymorphy3", "uk") is not get_backend("pymorphy3", "ru")


def test_simplemma_unsupported_language():
    with pytest.raises(UnsupportedLanguageError):
        get_backend("simplemma", "tlh")   # valid ISO 639-3 code, but simplemma has no data for it


def test_lemmatize_casefolded():
    assert get_backend("simplemma", "uk").lemmatize("Мої друзі бігали") == ["мій", "друг", "бігати"]
    assert get_backend("pymorphy3", "uk").lemmatize("п'ять книг")[0] == "п'ять"


def test_custom_callable():
    b = get_backend(lambda text, lang: text.split(), "en")
    assert b.lemmatize("Hello World") == ["hello", "world"]


def test_instance_language_mismatch():
    b = get_backend("pymorphy3", "uk")
    with pytest.raises(UnsupportedLanguageError):
        get_backend(b, "ru")


def test_introspection():
    assert available_backends()["pymorphy3"] == ["ru", "uk"]
    assert "pymorphy3" in backends_for("ru_RU") and "pymorphy3" not in backends_for("de")
