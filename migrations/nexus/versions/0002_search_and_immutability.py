"""Chinese lexical search and immutable lecture text."""
from alembic import op
from sqlalchemy import inspect, text

revision='0002_search'
down_revision='0001_nexus'
branch_labels=None
depends_on=None


def upgrade():
    connection=op.get_bind()
    if 'search_text' not in {c['name'] for c in inspect(connection).get_columns('chunks')}:
        op.execute("ALTER TABLE chunks ADD COLUMN search_text TEXT NOT NULL DEFAULT ''")
    from app.nexus.retrieval import terms
    for row in connection.execute(text('SELECT id,content FROM chunks')).mappings().all():
        connection.execute(text('UPDATE chunks SET search_text=:value WHERE id=:identifier'),
                           {'value':' '.join(sorted(terms(row['content']))),'identifier':row['id']})
    op.execute('DROP INDEX IF EXISTS ix_chunks_fts')
    op.execute("CREATE INDEX ix_chunks_fts ON chunks USING gin(to_tsvector('simple', search_text))")
    op.execute('''CREATE OR REPLACE FUNCTION nexus_immutable_lecture() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF NEW.content IS DISTINCT FROM OLD.content OR NEW.sha256 IS DISTINCT FROM OLD.sha256
           OR NEW.material_id IS DISTINCT FROM OLD.material_id OR NEW.number IS DISTINCT FROM OLD.number
           OR NEW.class_id IS DISTINCT FROM OLD.class_id THEN
          RAISE EXCEPTION 'lecture version text and identity are immutable';
        END IF;
        RETURN NEW;
      END; $$''')
    op.execute('CREATE TRIGGER trg_immutable_lecture BEFORE UPDATE ON material_versions FOR EACH ROW EXECUTE FUNCTION nexus_immutable_lecture()')


def downgrade():
    raise RuntimeError('Restore an approved database backup instead of destructive downgrade')
