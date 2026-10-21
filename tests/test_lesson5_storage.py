from unittest.mock import patch
from app.chunks import split_chunks
from app.db import get_db
from app.hybrid_search import search
from app.lesson5_schema import migrate
from tests.support import Fixture


class StorageTests(Fixture):
    def test_mysql_empty_executemany_result(self):
        from app.db import MySQLResult
        result = MySQLResult(object())
        self.assertIsNone(result.lastrowid)
        self.assertEqual(result.rowcount, 0)

    def test_schema_seed_and_idempotency(self):
        with self.app.app_context():
            connection = get_db()
            migrate(connection)
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertTrue({"token_revocations", "tutor_agents", "tutor_agent_skills", "tutor_agent_materials", "conversations", "messages"} <= tables)
            seeds = connection.execute("SELECT name FROM skills WHERE class_id='A' ORDER BY id").fetchall()
            self.assertEqual([row[0] for row in seeds], ["数学解题引导", "语文解题引导"])

    def test_three_chunk_strategies_offsets(self):
        text = "# 数学\n\n" + "数学方程。" * 300 + "\n\n# 语文\n" + "阅读。" * 100
        for strategy in ("auto", "custom", "hierarchy"):
            chunks = split_chunks(text, strategy)
            self.assertEqual(chunks[0][1], 0)
            self.assertEqual(chunks[-1][2], len(text))
            self.assertTrue(all(text[start:end] == body and len(body) <= 800 for _, start, end, body in chunks))
            self.assertTrue(all(chunks[i][2] - chunks[i + 1][1] == 80 for i in range(len(chunks) - 1)))

    def test_rrf_qdrant_scope_and_id_consistency(self):
        self.login()
        material = self.upload()
        with self.app.app_context(), patch("app.hybrid_search.embed_text", return_value=[1.0, 0.0]):
            hits = search("数学方程", "A", material_ids=[material])
            self.assertEqual(len(hits), 1)
            self.assertAlmostEqual(hits[0]["score"], 2 / 61, places=6)
            row = get_db().execute("SELECT id,status FROM knowledge_chunks WHERE material_id=?", (material,)).fetchone()
            self.assertEqual(row["status"], "ready")
            self.assertIn(row["id"], self.vectors.points)
            self.assertEqual(self.vectors.filters[-1], ("A", [material], 20))
            self.assertEqual(search("数学", "B", material_ids=[material]), [])
            self.assertEqual(search("数学", "A", material_ids=[]), [])
