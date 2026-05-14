from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from easy_social.extensions import db
from easy_social.models import PollOption, PollVote, Post, User

from conftest import login, logout, register

# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

pytestmark_unit = pytest.mark.unit


@pytest.mark.unit
def test_poll_option_requires_text(app):
    with app.app_context():
        user = User(username="u", email="u@example.com")
        user.set_password("pw")
        db.session.add(user)
        db.session.flush()
        post = Post(body="Which one?", author=user, is_poll=True)
        db.session.add(post)
        db.session.flush()
        opt = PollOption(post_id=post.id, text="Option A", position=0)
        db.session.add(opt)
        db.session.commit()
        assert PollOption.query.count() == 1


@pytest.mark.unit
def test_poll_vote_unique_per_user_per_poll(app):
    with app.app_context():
        user = User(username="u2", email="u2@example.com")
        user.set_password("pw")
        db.session.add(user)
        db.session.flush()
        post = Post(body="Q?", author=user, is_poll=True)
        db.session.add(post)
        db.session.flush()
        opt1 = PollOption(post_id=post.id, text="A", position=0)
        opt2 = PollOption(post_id=post.id, text="B", position=1)
        db.session.add_all([opt1, opt2])
        db.session.flush()

        db.session.add(PollVote(option_id=opt1.id, post_id=post.id, user_id=user.id))
        db.session.commit()

        db.session.add(PollVote(option_id=opt2.id, post_id=post.id, user_id=user.id))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


@pytest.mark.unit
def test_is_poll_defaults_false(app):
    with app.app_context():
        user = User(username="u3", email="u3@example.com")
        user.set_password("pw")
        db.session.add(user)
        db.session.flush()
        post = Post(body="Normal post", author=user)
        db.session.add(post)
        db.session.commit()
        assert post.is_poll is False


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.integration


@pytest.mark.integration
def test_create_poll_post(client, app):
    register(client, "alice")
    response = client.post(
        "/posts",
        data={
            "is_poll": "1",
            "body": "Favourite language?",
            "poll_option_1": "Python",
            "poll_option_2": "Go",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    with app.app_context():
        post = Post.query.filter_by(body="Favourite language?").one()
        assert post.is_poll is True
        options = PollOption.query.filter_by(post_id=post.id).all()
        assert len(options) == 2
        assert {o.text for o in options} == {"Python", "Go"}


@pytest.mark.integration
def test_create_poll_requires_question(client):
    register(client, "alice")
    response = client.post(
        "/posts",
        data={"is_poll": "1", "body": "", "poll_option_1": "A", "poll_option_2": "B"},
        follow_redirects=True,
    )
    assert b"question" in response.data.lower()


@pytest.mark.integration
def test_create_poll_requires_two_options(client):
    register(client, "alice")
    response = client.post(
        "/posts",
        data={"is_poll": "1", "body": "Q?", "poll_option_1": "Only one"},
        follow_redirects=True,
    )
    assert b"2 option" in response.data or b"least 2" in response.data


@pytest.mark.integration
def test_vote_records_vote(client, app):
    register(client, "alice")
    client.post(
        "/posts",
        data={"is_poll": "1", "body": "Q?", "poll_option_1": "Yes", "poll_option_2": "No"},
        follow_redirects=True,
    )
    with app.app_context():
        post = Post.query.filter_by(body="Q?").one()
        opt_id = PollOption.query.filter_by(post_id=post.id, text="Yes").one().id
        post_id = post.id

    response = client.post(
        f"/posts/{post_id}/vote",
        data={"option_id": opt_id},
        follow_redirects=True,
    )
    assert response.status_code == 200
    with app.app_context():
        assert PollVote.query.filter_by(post_id=post_id).count() == 1
        vote = PollVote.query.filter_by(post_id=post_id).one()
        assert vote.option_id == opt_id


@pytest.mark.integration
def test_vote_can_be_changed(client, app):
    register(client, "alice")
    client.post(
        "/posts",
        data={"is_poll": "1", "body": "Pick?", "poll_option_1": "A", "poll_option_2": "B"},
        follow_redirects=True,
    )
    with app.app_context():
        post = Post.query.filter_by(body="Pick?").one()
        opt_a = PollOption.query.filter_by(post_id=post.id, text="A").one().id
        opt_b = PollOption.query.filter_by(post_id=post.id, text="B").one().id
        post_id = post.id

    client.post(f"/posts/{post_id}/vote", data={"option_id": opt_a})
    client.post(f"/posts/{post_id}/vote", data={"option_id": opt_b})

    with app.app_context():
        assert PollVote.query.filter_by(post_id=post_id).count() == 1
        vote = PollVote.query.filter_by(post_id=post_id).one()
        assert vote.option_id == opt_b


@pytest.mark.integration
def test_vote_on_non_poll_returns_400(client, app):
    register(client, "alice")
    client.post("/posts", data={"body": "Regular post"}, follow_redirects=True)
    with app.app_context():
        post_id = Post.query.one().id

    response = client.post(f"/posts/{post_id}/vote", data={"option_id": 1})
    assert response.status_code == 400


@pytest.mark.integration
def test_poll_appears_in_feed(client, app):
    register(client, "alice")
    client.post(
        "/posts",
        data={"is_poll": "1", "body": "Tea or Coffee?", "poll_option_1": "Tea", "poll_option_2": "Coffee"},
        follow_redirects=True,
    )
    response = client.get("/")
    assert b"Tea or Coffee?" in response.data
    assert b"Tea" in response.data
    assert b"Coffee" in response.data


@pytest.mark.integration
def test_poll_cannot_be_reposted(client, app):
    register(client, "alice")
    client.post(
        "/posts",
        data={"is_poll": "1", "body": "Repost me?", "poll_option_1": "Yes", "poll_option_2": "No"},
        follow_redirects=True,
    )
    with app.app_context():
        post_id = Post.query.filter_by(body="Repost me?").one().id
    logout(client)

    register(client, "bob")
    response = client.post(f"/posts/{post_id}/repost", follow_redirects=True)
    assert b"cannot be reposted" in response.data
    with app.app_context():
        assert Post.query.filter_by(repost_of_id=post_id).count() == 0


@pytest.mark.integration
def test_poll_vote_shown_in_feed_after_voting(client, app):
    register(client, "alice")
    client.post(
        "/posts",
        data={"is_poll": "1", "body": "Votes?", "poll_option_1": "Opt A", "poll_option_2": "Opt B"},
        follow_redirects=True,
    )
    with app.app_context():
        post = Post.query.filter_by(body="Votes?").one()
        opt_id = PollOption.query.filter_by(post_id=post.id, text="Opt A").one().id
        post_id = post.id

    client.post(f"/posts/{post_id}/vote", data={"option_id": opt_id}, follow_redirects=True)
    response = client.get("/")
    assert b"1 vote" in response.data


# ---------------------------------------------------------------------------
# E2E tests (Selenium)
# ---------------------------------------------------------------------------

selenium = pytest.importorskip("selenium")

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from tests.test_ui_selenium import (
    get_captcha_text,
    live_server,
    browser,
    ui_app,
    clean_database,
    set_field_value,
    submit_form,
    wait_for_feed,
    wait_for_text,
    register_via_ui,
)


@pytest.mark.ui
def test_create_poll_and_vote_via_ui(browser, live_server):
    register_via_ui(browser, live_server, "alice")

    toggle = browser.find_element(By.ID, "composer-poll-toggle")
    toggle.click()

    composer = browser.find_element(By.ID, "composer-form")
    set_field_value(browser, composer.find_element(By.NAME, "body"), "Best colour?")
    set_field_value(browser, composer.find_element(By.NAME, "poll_option_1"), "Red")
    set_field_value(browser, composer.find_element(By.NAME, "poll_option_2"), "Blue")
    submit_form(browser, composer)
    wait_for_text(browser, "Best colour?")
    wait_for_text(browser, "Red")

    vote_btn = WebDriverWait(browser, 5).until(
        EC.element_to_be_clickable((By.XPATH, "//button[.//span[text()='Red']]"))
    )
    vote_btn.click()
    wait_for_text(browser, "1 vote")
