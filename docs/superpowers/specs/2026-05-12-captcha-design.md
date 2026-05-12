# CAPTCHA Verification for Registration — Design Spec

**Date:** 2026-05-12
**Branch:** captcha
**Related Issue:** #1 Add CAPTCHA verification to registration flow

---

## Background

The Easy Social registration flow has no bot protection. Any automated script can create accounts repeatedly. This spec adds a server-side graphical CAPTCHA step to the registration page.

## Scope

Only the registration route is protected. Login is out of scope.

---

## Architecture

### Data Flow

```
GET /auth/register
  → render register.html (contains <img src="/auth/captcha.png">)

GET /auth/captcha.png
  → generate 5-char random uppercase alphanumeric text
  → store in session['captcha_answer']
  → return PNG image bytes (Content-Type: image/png)

POST /auth/register
  → compare form['captcha'] vs session['captcha_answer'] (case-insensitive)
  → FAIL: flash error, pop session key, re-render page (img tag auto-fetches new image)
  → PASS: pop session key, proceed to create user account
```

---

## Components

### `easy_social/captcha.py`

Three pure functions with no Flask dependency:

| Function | Signature | Purpose |
|---|---|---|
| `generate_captcha_text` | `(length: int = 5) -> str` | Returns random uppercase alphanumeric string |
| `build_captcha_image` | `(text: str) -> bytes` | Renders PNG via `captcha` library, returns raw bytes |
| `validate_captcha` | `(stored: str, user_input: str) -> bool` | Case-insensitive equality check; returns False if either arg is empty |

### `easy_social/auth.py`

**New route:** `GET /auth/captcha.png`
- Calls `generate_captcha_text()`, stores result in `session['captcha_answer']`
- Calls `build_captcha_image(text)`, returns `Response` with `Content-Type: image/png` and `Cache-Control: no-store`

**Modified route:** `POST /auth/register`
- Before existing validation, call `validate_captcha(session.pop('captcha_answer', ''), request.form.get('captcha', ''))`
- On failure: `flash("Incorrect CAPTCHA. Please try again.", "error")` and re-render (no redirect, so the new captcha image is fetched automatically)
- On success: continue with existing username/email/password validation

### `easy_social/templates/auth/register.html`

Add below the password field, above the submit button:

```html
<label>
  CAPTCHA
  <img src="{{ url_for('auth.captcha_image') }}" alt="CAPTCHA" id="captcha-img">
  <a href="#" id="captcha-refresh">看不清楚？重新整理</a>
  <input name="captcha" autocomplete="off" required placeholder="輸入圖中文字">
</label>
```

A small inline `<script>` handles the refresh link by appending `?t=Date.now()` to force a new image fetch.

### Dependencies

Add `captcha>=0.6.0` to `pyproject.toml` dependencies and `requirements.txt`.

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| CAPTCHA answer missing from session (e.g., session expired) | `validate_captcha` receives empty string → returns False → same error flash |
| User submits empty captcha field | HTML `required` blocks submission client-side; server-side also returns False |
| `captcha` library unavailable | Import error at startup — surfaced immediately, not silently |

---

## Testing

### Unit tests — `tests/test_captcha.py` (mark: `unit`)

- `test_generate_captcha_text_length` — default length is 5, custom length respected
- `test_generate_captcha_text_charset` — only uppercase letters and digits
- `test_validate_captcha_correct` — exact match returns True
- `test_validate_captcha_case_insensitive` — lowercase input matches uppercase stored
- `test_validate_captcha_wrong` — wrong text returns False
- `test_validate_captcha_empty_input` — empty string returns False
- `test_validate_captcha_empty_stored` — empty stored returns False
- `test_build_captcha_image_returns_png` — returned bytes start with PNG magic bytes `\x89PNG`

### Integration tests — `tests/test_auth.py` (mark: `integration`)

Use `client.session_transaction()` to pre-set `session['captcha_answer'] = 'ABCDE'` before each POST.

- `test_register_wrong_captcha_is_rejected` — POST with wrong captcha → 200, error flash visible, no user created
- `test_register_correct_captcha_succeeds` — POST with correct captcha → redirect to feed, user exists in DB
- `test_captcha_image_route_returns_png` — GET `/auth/captcha.png` → 200, Content-Type `image/png`, session contains `captcha_answer`
- `test_captcha_refreshes_on_wrong_attempt` — after failed POST, session no longer contains old answer (it was popped)

### Existing tests

The existing `conftest.register()` helper does not include a captcha field. Update it to also pre-set the session captcha answer so all existing registration-dependent tests continue to pass without modification.
