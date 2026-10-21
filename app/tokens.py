"""Short-lived bearer tokens for the classroom API demonstration."""
from datetime import datetime, timedelta, timezone
import hashlib
import uuid

import jwt
from flask import current_app

TOKEN_TTL = timedelta(minutes=30)


def _signing_key():
    # Separate the JWT signing key from Flask's cookie signing purpose.
    return hashlib.sha256(("campusclaw:jwt:" + current_app.secret_key).encode("utf-8")).digest()


def issue_token(user):
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(user["id"]),
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + TOKEN_TTL,
    }
    return jwt.encode(claims, _signing_key(), algorithm="HS256")


def verify_token(token):
    claims = jwt.decode(
        token,
        _signing_key(),
        algorithms=["HS256"],
        options={"require": ["sub", "jti", "iat", "exp"]},
    )
    if set(claims) != {"sub", "jti", "iat", "exp"} or not isinstance(claims["jti"], str) or not claims["jti"]:
        raise jwt.InvalidTokenError("invalid core claims")
    from .db import get_db
    if get_db().execute("SELECT jti FROM token_revocations WHERE jti=?", (claims["jti"],)).fetchone():
        raise jwt.InvalidTokenError("revoked token")
    return claims


def revoke(claims):
    from .db import get_db
    if claims and claims.get("jti"):
        connection = get_db()
        connection.execute("INSERT OR IGNORE INTO token_revocations (jti,expires_at) VALUES (?,?)", (claims["jti"], claims["exp"]))
        connection.commit()
