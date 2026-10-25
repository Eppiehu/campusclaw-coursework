"""Initial PostgreSQL Nexus schema with vector and full-text indexes."""
from alembic import op
from app.nexus.models import Base

revision='0001_nexus'
down_revision=None
branch_labels=None
depends_on=None


def upgrade():
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    Base.metadata.create_all(op.get_bind())
    op.execute("CREATE INDEX ix_chunks_fts ON chunks USING gin(to_tsvector('simple', content))")
    op.execute('CREATE INDEX ix_chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops)')


def downgrade():
    raise RuntimeError('Destructive downgrade is disabled; restore an approved database backup instead')
