from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import desc, func, or_
from sqlalchemy.orm import joinedload, subqueryload

from .extensions import db
from .media import save_media
from .models import Comment, PollOption, PollVote, Post, User, followers

bp = Blueprint("social", __name__)


def _post_query():
    return Post.query.options(
        joinedload(Post.author),
        joinedload(Post.repost_of).joinedload(Post.author),
        subqueryload(Post.poll_options),
    )


def _comment_counts_for_posts(posts: list[Post]) -> dict[int, int]:
    post_ids = {post.display_post.id for post in posts}
    if not post_ids:
        return {}

    counts = dict.fromkeys(post_ids, 0)
    rows = (
        db.session.query(Comment.post_id, func.count(Comment.id))
        .filter(Comment.post_id.in_(post_ids))
        .group_by(Comment.post_id)
        .all()
    )
    counts.update({post_id: count for post_id, count in rows})
    return counts


def _poll_data_for_posts(posts: list[Post]) -> dict[int, dict]:
    poll_posts = [p.display_post for p in posts if p.display_post.is_poll]
    if not poll_posts:
        return {}

    option_ids = [o.id for p in poll_posts for o in p.poll_options]
    poll_post_ids = {p.id for p in poll_posts}

    if not option_ids:
        return {}

    vote_counts: dict[int, int] = dict.fromkeys(option_ids, 0)
    for option_id, cnt in (
        db.session.query(PollVote.option_id, func.count(PollVote.id))
        .filter(PollVote.option_id.in_(option_ids))
        .group_by(PollVote.option_id)
        .all()
    ):
        vote_counts[option_id] = cnt

    user_votes: dict[int, int] = {}
    if current_user.is_authenticated:
        for post_id, option_id in (
            db.session.query(PollVote.post_id, PollVote.option_id)
            .filter(
                PollVote.post_id.in_(poll_post_ids),
                PollVote.user_id == current_user.id,
            )
            .all()
        ):
            user_votes[post_id] = option_id

    result: dict[int, dict] = {}
    for post in poll_posts:
        total = sum(vote_counts.get(o.id, 0) for o in post.poll_options)
        user_vote_id = user_votes.get(post.id)
        result[post.id] = {
            "options": [
                {
                    "id": o.id,
                    "text": o.text,
                    "votes": vote_counts.get(o.id, 0),
                    "pct": round(vote_counts.get(o.id, 0) / total * 100) if total else 0,
                    "is_user_vote": o.id == user_vote_id,
                }
                for o in post.poll_options
            ],
            "total_votes": total,
            "user_vote_option_id": user_vote_id,
        }
    return result


def _followed_user_ids(users: list[User]) -> set[int]:
    user_ids = [user.id for user in users]
    if not user_ids:
        return set()

    return {
        followed_id
        for (followed_id,) in db.session.query(followers.c.followed_id)
        .filter(
            followers.c.follower_id == current_user.id,
            followers.c.followed_id.in_(user_ids),
        )
        .all()
    }


@bp.route("/")
@login_required
def feed():
    followed_ids = db.session.query(followers.c.followed_id).filter(
        followers.c.follower_id == current_user.id
    )
    posts = (
        _post_query()
        .filter(or_(Post.author_id == current_user.id, Post.author_id.in_(followed_ids)))
        .order_by(desc(Post.created_at))
        .limit(100)
        .all()
    )
    return render_template(
        "social/feed.html",
        posts=posts,
        comment_counts=_comment_counts_for_posts(posts),
        poll_data=_poll_data_for_posts(posts),
    )


@bp.route("/explore")
@login_required
def explore():
    posts = _post_query().order_by(desc(Post.created_at)).limit(100).all()
    users = User.query.filter(User.id != current_user.id).order_by(User.username).limit(50).all()
    return render_template(
        "social/explore.html",
        posts=posts,
        users=users,
        comment_counts=_comment_counts_for_posts(posts),
        followed_user_ids=_followed_user_ids(users),
        poll_data=_poll_data_for_posts(posts),
    )


@bp.post("/posts")
@login_required
def create_post():
    body = request.form.get("body", "").strip()
    is_poll = "is_poll" in request.form

    if is_poll:
        options = [
            request.form.get(f"poll_option_{i}", "").strip()
            for i in range(1, 5)
        ]
        options = [o for o in options if o]
        if not body:
            flash("A poll needs a question.", "error")
            return redirect(request.referrer or url_for("social.feed"))
        if len(options) < 2:
            flash("A poll needs at least 2 options.", "error")
            return redirect(request.referrer or url_for("social.feed"))
        post = Post(body=body, author=current_user, is_poll=True)
        db.session.add(post)
        db.session.flush()
        for i, text in enumerate(options):
            db.session.add(PollOption(post_id=post.id, text=text, position=i))
        db.session.commit()
        return redirect(url_for("social.feed"))

    try:
        media_filename, media_type = save_media(request.files.get("media"))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(request.referrer or url_for("social.feed"))

    if not body and not media_filename:
        flash("Add text, an image, or a video before posting.", "error")
        return redirect(request.referrer or url_for("social.feed"))

    post = Post(
        body=body,
        media_filename=media_filename,
        media_type=media_type,
        author=current_user,
    )
    db.session.add(post)
    db.session.commit()
    return redirect(url_for("social.feed"))


@bp.get("/posts/<int:post_id>")
@login_required
def post_detail(post_id: int):
    post = _post_query().filter(Post.id == post_id).first_or_404()
    comments = post.comments.order_by(Comment.created_at.asc()).all()
    return render_template(
        "social/post_detail.html",
        post=post,
        comments=comments,
        comment_counts={post.display_post.id: len(comments)},
        poll_data=_poll_data_for_posts([post]),
    )


@bp.post("/posts/<int:post_id>/vote")
@login_required
def vote(post_id: int):
    post = db.get_or_404(Post, post_id)
    target = post.display_post
    if not target.is_poll:
        abort(400)
    option_id = request.form.get("option_id", type=int)
    option = PollOption.query.filter_by(id=option_id, post_id=target.id).first_or_404()

    existing = PollVote.query.filter_by(user_id=current_user.id, post_id=target.id).first()
    if existing:
        existing.option_id = option.id
    else:
        db.session.add(PollVote(option_id=option.id, post_id=target.id, user_id=current_user.id))
    db.session.commit()
    return redirect(request.referrer or url_for("social.feed"))


@bp.post("/posts/<int:post_id>/comments")
@login_required
def add_comment(post_id: int):
    post = db.get_or_404(Post, post_id)
    body = request.form.get("body", "").strip()
    if not body:
        flash("Comment cannot be empty.", "error")
    else:
        db.session.add(Comment(body=body, author=current_user, post=post))
        db.session.commit()
    return redirect(url_for("social.post_detail", post_id=post.id))


@bp.post("/posts/<int:post_id>/repost")
@login_required
def repost(post_id: int):
    original = db.get_or_404(Post, post_id).display_post
    if original.is_poll:
        flash("Poll posts cannot be reposted.", "error")
        return redirect(request.referrer or url_for("social.feed"))
    if original.author_id == current_user.id:
        flash("You cannot repost your own post.", "error")
        return redirect(request.referrer or url_for("social.feed"))

    existing = Post.query.filter_by(author_id=current_user.id, repost_of_id=original.id).first()
    if existing:
        flash("You already reposted this.", "error")
        return redirect(request.referrer or url_for("social.feed"))

    db.session.add(Post(author=current_user, repost_of=original))
    db.session.commit()
    return redirect(request.referrer or url_for("social.feed"))


@bp.route("/users/<username>")
@login_required
def profile(username: str):
    user = User.query.filter_by(username=username).first_or_404()
    posts = (
        _post_query()
        .filter(Post.author_id == user.id)
        .order_by(desc(Post.created_at))
        .all()
    )
    return render_template(
        "social/profile.html",
        profile_user=user,
        posts=posts,
        comment_counts=_comment_counts_for_posts(posts),
        poll_data=_poll_data_for_posts(posts),
    )


@bp.post("/users/<username>/follow")
@login_required
def follow(username: str):
    user = User.query.filter_by(username=username).first_or_404()
    current_user.follow(user)
    db.session.commit()
    return redirect(request.referrer or url_for("social.profile", username=user.username))


@bp.post("/users/<username>/unfollow")
@login_required
def unfollow(username: str):
    user = User.query.filter_by(username=username).first_or_404()
    current_user.unfollow(user)
    db.session.commit()
    return redirect(request.referrer or url_for("social.profile", username=user.username))
