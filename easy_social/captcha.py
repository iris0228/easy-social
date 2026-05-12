from __future__ import annotations

import random
import string

from captcha.image import ImageCaptcha

_CHARSET = string.ascii_uppercase + string.digits


def generate_captcha_text(length: int = 5) -> str:
    return "".join(random.choices(_CHARSET, k=length))


def build_captcha_image(text: str) -> bytes:
    buf = ImageCaptcha().generate(text)
    return buf.getvalue()


def validate_captcha(stored: str, user_input: str) -> bool:
    if not stored or not user_input:
        return False
    return stored.upper() == user_input.upper()
