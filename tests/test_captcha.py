from __future__ import annotations

import string

import pytest

pytestmark = pytest.mark.unit


def test_generate_captcha_text_default_length():
    from easy_social.captcha import generate_captcha_text
    text = generate_captcha_text()
    assert len(text) == 5


def test_generate_captcha_text_custom_length():
    from easy_social.captcha import generate_captcha_text
    text = generate_captcha_text(length=8)
    assert len(text) == 8


def test_generate_captcha_text_charset():
    from easy_social.captcha import generate_captcha_text
    allowed = set(string.ascii_uppercase + string.digits)
    for _ in range(20):
        text = generate_captcha_text()
        assert all(c in allowed for c in text)


def test_build_captcha_image_returns_png_bytes():
    from easy_social.captcha import build_captcha_image
    data = build_captcha_image("ABCDE")
    assert isinstance(data, bytes)
    assert data[:4] == b'\x89PNG'


def test_validate_captcha_exact_match():
    from easy_social.captcha import validate_captcha
    assert validate_captcha("ABCDE", "ABCDE") is True


def test_validate_captcha_case_insensitive():
    from easy_social.captcha import validate_captcha
    assert validate_captcha("ABCDE", "abcde") is True


def test_validate_captcha_wrong_text():
    from easy_social.captcha import validate_captcha
    assert validate_captcha("ABCDE", "ZZZZZ") is False


def test_validate_captcha_empty_input():
    from easy_social.captcha import validate_captcha
    assert validate_captcha("ABCDE", "") is False


def test_validate_captcha_empty_stored():
    from easy_social.captcha import validate_captcha
    assert validate_captcha("", "ABCDE") is False
