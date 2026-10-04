import pytest

from bot.words import parse_words


def test_parse_strips_markdown_and_duplicates():
    text = """```json
    [
      {"tr": "kedi", "uz": "mushuk", "example_tr": "Kedi uyuyor.", "example_uz": "Mushuk uxlayapti."},
      {"tr": "KEDI", "uz": "mushuk"},
      {"tr": "", "uz": "bo'sh"},
      {"uz": "kalitsiz"},
      "xato"
    ]
    ```"""
    words = parse_words(text)
    assert len(words) == 1
    assert words[0]["tr"] == "kedi"
    assert words[0]["example_uz"] == "Mushuk uxlayapti."


def test_parse_without_json_raises():
    with pytest.raises(ValueError):
        parse_words("kechirasiz, bajara olmayman")


def test_gemini_text_extraction():
    from bot.words import gemini_text

    data = {"candidates": [{"content": {"parts": [{"text": "[{"}, {"text": "}]"}]}}]}
    assert gemini_text(data) == "[{}]"

    for bad in ({}, {"candidates": []}, {"candidates": [{"content": {"parts": [{"text": "  "}]}}]}):
        with pytest.raises(ValueError):
            gemini_text(bad)
