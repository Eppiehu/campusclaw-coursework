from datetime import timedelta
import functools
import os
import uuid
import jwt
from flask import abort, g, request
from sqlalchemy import select
from .db import transaction, audit
from .models import User, RevokedToken, now


def signing_key():
    value = os.environ.get('NEXUS_SIGNING_KEY', '')
    if len(value) < 32:
        raise RuntimeError('NEXUS_SIGNING_KEY must have at least 32 characters')
    return value


def issue(user):
    stamp = now()
    return jwt.encode(dict(sub=str(user.id), jti=uuid.uuid4().hex, iat=stamp,
                           exp=stamp+timedelta(minutes=30), iss='campusclaw-nexus', aud='nexus-api'),
                      signing_key(), algorithm='HS256')


def authenticate(db, token):
    try:
        claims = jwt.decode(token, signing_key(), algorithms=['HS256'],
                            issuer='campusclaw-nexus', audience='nexus-api',
                            options={'require': ['sub','jti','iat','exp','iss','aud']})
        if db.get(RevokedToken, claims['jti']):
            raise jwt.InvalidTokenError('revoked')
        user = db.get(User, int(claims['sub']))
        if not user:
            raise jwt.InvalidTokenError('unknown user')
        return user, claims
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise PermissionError('登录已过期，请重新登录') from None


def require(role=None):
    def decorate(fn):
        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            scheme, _, token = request.headers.get('Authorization','').partition(' ')
            if scheme.lower() != 'bearer' or not token:
                abort(401)
            with transaction() as db:
                try:
                    user, claims = authenticate(db, token)
                except PermissionError:
                    abort(401)
                if role and user.role != role:
                    audit(db,user,'permission.denied',request.path,success=False,request_id=g.request_id)
                    db.commit()
                    abort(403)
                g.user, g.token, g.claims = user, token, claims
            return fn(*args, **kwargs)
        return wrapped
    return decorate


def scoped(db, model, identifier, user, owner=False, lock=False):
    query = select(model).where(model.id==identifier, model.class_id==user.class_id)
    if owner:
        query = query.where(model.user_id==user.id)
    if lock:
        query = query.with_for_update()
    row = db.scalar(query)
    if row is None:
        abort(404)
    return row
