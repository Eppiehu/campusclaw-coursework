from functools import wraps

from flask import Blueprint, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from .db import get_db
from .api_docs import api_doc, object_schema

bp = Blueprint("auth", __name__)


def authenticate(username, password):
    user = get_db().execute(
        "SELECT id, username, role, class_id, password_hash FROM users WHERE username = ?", (username,)
    ).fetchone()
    return user if user is not None and check_password_hash(user["password_hash"], password) else None


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if g.user is None:
            if request.path.startswith("/api/"):
                return jsonify(error="请先登录"), 401
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapper


def teacher_required(view):
    @wraps(view)
    @login_required
    def wrapper(*args, **kwargs):
        if g.user["role"] != "teacher":
            return jsonify(error="仅教师可以执行此操作"), 403
        return view(*args, **kwargs)
    return wrapper


def establish_login(user):
    from .tokens import issue_token, revoke, verify_token
    from jwt import InvalidTokenError
    old = request.headers.get("Authorization", "")
    if old.lower().startswith("bearer "):
        try:
            revoke(verify_token(old.split(" ", 1)[1]))
        except (InvalidTokenError, ValueError, TypeError):
            pass
    session.clear()
    session.update(user_id=user["id"], role=user["role"], class_id=user["class_id"])
    token = issue_token(user)
    claims = verify_token(token)
    session["token_jti"], session["token_exp"] = claims["jti"], claims["exp"]
    return token


@bp.get("/")
def index():
    return redirect(url_for("materials.list_page" if g.user else "auth.login"))


@bp.post("/api/login")
@bp.route("/login", methods=["GET", "POST"])
@api_doc("用户名密码登录，同时建立Session和JWT", auth=False, tags=["auth"], body=object_schema({"username": {"type": "string"}, "password": {"type": "string", "format": "password"}}, ["username", "password"]))
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
    user = authenticate(username, password)
    if user is None:
        session.clear()
        if is_json:
            return jsonify(error="用户名或密码错误"), 401
        return render_template("login.html", error="用户名或密码错误", username=username), 401

    token = establish_login(user)
    if is_json:
        return jsonify(token=token, username=user["username"], role=user["role"], class_id=user["class_id"])
    return redirect(url_for("materials.list_page"))


@bp.post("/api/token/login")
@api_doc("兼容Token登录入口", auth=False, tags=["auth"], body=object_schema({"username": {"type": "string"}, "password": {"type": "string"}}, ["username", "password"]))
def token_login():
    from .tokens import TOKEN_TTL, issue_token

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="需要 JSON 用户名和密码"), 400
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    user = authenticate(username, password)
    if user is None:
        session.clear()
        return jsonify(error="用户名或密码错误"), 401

    # The cookie keeps existing Jinja pages working; API authorization can use
    # the token independently, including when no session cookie is present.
    token = establish_login(user)
    return jsonify(
        username=user["username"],
        role=user["role"],
        class_id=user["class_id"],
        access_token=token,
        token_type="Bearer",
        expires_in=int(TOKEN_TTL.total_seconds()),
    )


@bp.post("/api/logout")
@bp.post("/logout")
@api_doc("吊销当前jti并清除Session", tags=["auth"])
def logout():
    from .tokens import revoke
    claims = g.token_claims or ({"jti": session["token_jti"], "exp": session["token_exp"]} if session.get("token_jti") else None)
    revoke(claims)
    session.clear()
    if request.path.startswith("/api/") or request.is_json:
        return jsonify(status="ok")
    return redirect(url_for("auth.login"))


@bp.get("/api/me")
@api_doc("读取数据库中的当前身份", tags=["auth"])
@login_required
def current_user():
    return jsonify(user={key: g.user[key] for key in ("id", "username", "role", "class_id")})
