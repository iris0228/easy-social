import random
import string


def generate_captcha_text(length: int = 5) -> str:
    """Generate a random CAPTCHA text."""
    characters = string.ascii_uppercase + string.digits
    return "".join(random.choice(characters) for _ in range(length))


def validate_captcha(user_input: str | None, expected: str | None) -> bool:
    """Validate user CAPTCHA input against expected CAPTCHA text."""
    if not user_input or not expected:
        return False
    return user_input.strip().upper() == expected.strip().upper()
