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
        DATABASE_URL=os.environ.get("DATABASE_URL"),
        QDRANT_URL=os.environ.get("QDRANT_URL", "http://127.0.0.1:6333"),
        QDRANT_COLLECTION=os.environ.get("QDRANT_COLLECTION", "campusclaw_chunks"),
        SEARCH_MAX_RESULTS=int(os.environ.get("SEARCH_MAX_RESULTS", "20")),
        UPLOAD_FOLDER=str(root / "uploads"),
        MAX_CONTENT_LENGTH=1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        MCP_SERVER_COMMAND=os.environ.get("MCP_SERVER_COMMAND", ""),
        MCP_ALLOWED_TOOLS=os.environ.get("MCP_ALLOWED_TOOLS", "calculator,current_time").split(","),
    )
    if test_config:
        app.config.update(test_config)
    if not app.testing and not (app.config.get("DATABASE_URL") or "").startswith("mysql://"):
        raise RuntimeError("第5课运行需要DATABASE_URL=mysql://...；SQLite仅用于隔离回归测试")
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)

    app.teardown_appcontext(db.close_db)

    @app.before_request
    def load_current_user():
        g.user = None
        g.token_claims = None
        authorization = request.headers.get("Authorization")
        public_login = request.path in {"/login", "/api/login", "/api/token/login"}
        bearer_required = request.path.startswith("/api/") and not public_login
        if not public_login and (bearer_required or (authorization is not None and request.path == "/logout")):
            from jwt import InvalidTokenError
            from .tokens import verify_token

            scheme, separator, token = (authorization or "").partition(" ")
            if scheme.lower() != "bearer" or not separator or not token.strip():
                return jsonify(error="无效或过期的 token"), 401
            try:
                claims = verify_token(token.strip())
                g.token_claims = claims
                user_id = int(claims["sub"])
            except (InvalidTokenError, ValueError, TypeError):
                return jsonify(error="无效或过期的 token"), 401
            g.user = db.get_db().execute(
                "SELECT id, username, role, class_id FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if g.user is None:
                g.user = None
                return jsonify(error="无效或过期的 token"), 401
            return None

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

    @app.errorhandler(ValueError)
    def bad_input(error):
        return jsonify(error=str(error)), 400

    from .auth import bp as auth_bp
    from .materials import bp as materials_bp
    from .knowledge_api import bp as knowledge_bp
    from .tutor_api import bp as tutor_bp
    from .conversation_api import bp as conversation_bp
    from .openapi import bp as openapi_bp
    from .tutor_pages import bp as tutor_pages_bp
    from .prompt_api import bp as prompt_bp
    from .mcp_client import bp as mcp_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(materials_bp)
    app.register_blueprint(knowledge_bp)
    app.register_blueprint(tutor_bp)
    app.register_blueprint(conversation_bp)
    app.register_blueprint(openapi_bp)
    app.register_blueprint(tutor_pages_bp)
    app.register_blueprint(prompt_bp)
    app.register_blueprint(mcp_bp)
    return app
