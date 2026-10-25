from alembic import context
from sqlalchemy import text
from app.nexus.db import engine
from app.nexus.models import Base

with engine().connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()
