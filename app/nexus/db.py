from contextlib import contextmanager
import os
from functools import lru_cache
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import dotenv_values
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for _key,_value in dotenv_values(ROOT / '.env.nexus.local').items():
    if _key!='CAMPUSCLAW_EDITION' and _value is not None:os.environ.setdefault(_key,_value)


def engine(url=None):
    url = url or os.environ.get('NEXUS_DATABASE_URL', '')
    if not url.startswith('postgresql+psycopg://'):
        raise RuntimeError('NEXUS_DATABASE_URL must use PostgreSQL/psycopg')
    return _engine(url)


@lru_cache(maxsize=16)
def _engine(url):
    return create_engine(url, pool_pre_ping=True, pool_size=4, max_overflow=4, connect_args={'connect_timeout':8})


@contextmanager
def transaction(url=None):
    session = sessionmaker(engine(url), expire_on_commit=False)()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def audit(db, actor, action, resource='', details=None, success=True, request_id=None):
    from .models import Audit
    import uuid
    db.add(Audit(actor_id=actor.id if actor else None, class_id=actor.class_id if actor else '',
                 action=action, resource_id=str(resource), details=details or {}, success=success,
                 request_id=request_id or uuid.uuid4().hex))
