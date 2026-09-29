import os
from pathlib import Path

from flask import Flask, g, jsonify, request, session
from werkzeug.exceptions import RequestEntityTooLarge

from . import db


def create_app(test_config=None):
    app = Flask(__name__)
    secret = os.environ.get("SECRET_KEY")
    if not secret and not (test_config and test_config.get("SECRET_KEY")):
        raise RuntimeError("SECRET_KEY must be set in the environment")

    root = Path(__file__).resolve().parent.parent
    app.config.update(
        SECRET_KEY=secret,
        DATABASE=str(root / "data" / "app.db"),
        UPLOAD_FOLDER=str(root / "uploads"),
        MAX_CONTENT_LENGTH=1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if test_config:
        app.config.update(test_config)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)

    app.teardown_appcontext(db.close_db)

    @app.before_request
    def load_current_user():
        g.user = None
        user_id = session.get("user_id")
        if user_id is not None:
            g.user = db.get_db().execute(
                "SELECT id, username, role, class_id FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if g.user is None or g.user["role"] != session.get("role") or g.user["class_id"] != session.get("class_id"):
                session.clear()
                g.user = None

    @app.get("/health")
    def health():
        db.get_db().execute("SELECT 1").fetchone()
        return jsonify(status="ok")

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(_error):
        if request.path.startswith("/api/"):
            return jsonify(error="文件不得超过 1 MB"), 413
        return "文件不得超过 1 MB", 413

    from .auth import bp as auth_bp
    from .materials import bp as materials_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(materials_bp)
    return app
