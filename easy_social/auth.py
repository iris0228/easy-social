from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from .captcha import generate_captcha_text, validate_captcha
from .extensions import db
from .models import User

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("social.feed"))

    if request.method == "GET":
        session["captcha_text"] = generate_captcha_text()

    if request.method == "POST":
        captcha_input = request.form.get("captcha", "")
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        error = None
        if not validate_captcha(captcha_input, session.get("captcha_text", "")):
            flash("Invalid CAPTCHA. Please try again.", "error")
            session["captcha_text"] = generate_captcha_text()
            return render_template("auth/register.html", captcha_text=session.get("captcha_text", ""))
        elif len(username) > 40:
            error = "Username must be 40 characters or fewer."
        elif User.query.filter_by(username=username).first():
            error = "That username is already taken."
        elif User.query.filter_by(email=email).first():
            error = "That email is already registered."

        if error:
            flash(error, "error")
        else:
            user = User(username=username, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            return redirect(url_for("social.feed"))

    return render_template("auth/register.html", captcha_text=session.get("captcha_text", ""))


@bp.get("/captcha.png")
def captcha_image():
    import io
    from flask import Response
    from captcha.image import ImageCaptcha
    if "captcha_text" not in session:
        session["captcha_text"] = generate_captcha_text()
    image_bytes = ImageCaptcha().generate(session["captcha_text"]).getvalue()
    return Response(image_bytes, mimetype="image/png")


@bp.get("/captcha-hint")
def captcha_hint():
    """Test-only endpoint: returns the current session captcha text as JSON."""
    from flask import current_app, jsonify, abort
    if not current_app.config.get("TESTING"):
        abort(404)
    return jsonify({"captcha_text": session.get("captcha_text", "")})


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("social.feed"))

    if request.method == "POST":
        username_or_email = request.form.get("username_or_email", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter(
            (User.username == username_or_email)
            | (User.email == username_or_email.lower())
        ).first()

        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("social.feed"))

        flash("Invalid username/email or password.", "error")

    return render_template("auth/login.html")


@bp.post("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
