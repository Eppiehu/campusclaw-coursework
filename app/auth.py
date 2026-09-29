from functools import wraps

from flask import Blueprint, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from .db import get_db

bp = Blueprint("auth", __name__)


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if g.user is None:
            if request.path.startswith("/api/"):
                return jsonify(error="请先登录"), 401
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapper


@bp.get("/")
def index():
    return redirect(url_for("materials.list_page" if g.user else "auth.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if g.user:
            return redirect(url_for("materials.list_page"))
        return render_template("login.html")

    is_json = request.is_json
    data = request.get_json(silent=True) if is_json else request.form
    data = data if isinstance(data, dict) or not is_json else {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    user = get_db().execute(
        "SELECT id, username, role, class_id, password_hash FROM users WHERE username = ?", (username,)
    ).fetchone()
    if user is None or not check_password_hash(user["password_hash"], password):
        session.clear()
        if is_json:
            return jsonify(error="用户名或密码错误"), 401
        return render_template("login.html", error="用户名或密码错误", username=username), 401

    session.clear()
    session["user_id"] = user["id"]
    session["role"] = user["role"]
    session["class_id"] = user["class_id"]
    if is_json:
        return jsonify(username=user["username"], role=user["role"], class_id=user["class_id"])
    return redirect(url_for("materials.list_page"))


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@bp.get("/api/me")
@login_required
def current_user():
    return jsonify(user={key: g.user[key] for key in ("id", "username", "role", "class_id")})
