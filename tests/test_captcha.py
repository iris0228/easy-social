from __future__ import annotations

import string

import pytest

from conftest import register


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


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_register_page_sets_captcha_in_session(client):
    client.get("/auth/register")
    with client.session_transaction() as sess:
        assert "captcha_text" in sess
        assert len(sess["captcha_text"]) == 5


@pytest.mark.integration
def test_register_wrong_captcha_shows_error(client):
    client.get("/auth/register")
    response = client.post(
        "/auth/register",
        data={
            "username": "alice",
            "email": "alice@example.com",
            "password": "password",
            "captcha": "WRONG",
        },
        follow_redirects=True,
    )
    assert b"Invalid CAPTCHA" in response.data


@pytest.mark.integration
def test_register_correct_captcha_succeeds(client):
    response = register(client, "alice")
    assert response.status_code == 200
    assert b"Feed" in response.data


@pytest.mark.integration
def test_register_empty_captcha_fails(client):
    client.get("/auth/register")
    response = client.post(
        "/auth/register",
        data={
            "username": "alice",
            "email": "alice@example.com",
            "password": "password",
            "captcha": "",
        },
        follow_redirects=True,
    )
    assert b"Invalid CAPTCHA" in response.data


@pytest.mark.integration
def test_register_captcha_refreshed_after_failure(client):
    client.get("/auth/register")
    with client.session_transaction() as sess:
        first_captcha = sess["captcha_text"]

    client.post(
        "/auth/register",
        data={
            "username": "alice",
            "email": "alice@example.com",
            "password": "password",
            "captcha": "WRONG",
        },
        follow_redirects=True,
    )

    with client.session_transaction() as sess:
        assert sess["captcha_text"] != first_captcha


@pytest.mark.integration
def test_captcha_image_endpoint_returns_png(client):
    response = client.get("/auth/captcha.png")
    assert response.status_code == 200
    assert response.content_type == "image/png"
    assert response.data[:4] == b"\x89PNG"


@pytest.mark.integration
def test_authenticated_user_redirected_from_register(client):
    register(client, "alice")
    response = client.get("/auth/register")
    assert response.status_code == 302
    assert "/auth/register" not in response.headers["Location"]
