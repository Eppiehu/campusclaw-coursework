import io
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import jwt

from app import create_app
from scripts import init_db
from tests.support import MemoryVectors


class CampusClawTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.old_root, self.old_db = init_db.ROOT, init_db.DB_FILE
        init_db.ROOT = self.root
        init_db.DB_FILE = self.root / "data" / "app.db"
        init_db.init_database()
        self.app = create_app({
            "TESTING": True,
            "DATABASE_URL": None,
            "VECTOR_STORE": MemoryVectors(),
            "SECRET_KEY": "unit-test-key-only",
            "DATABASE": str(init_db.DB_FILE),
            "UPLOAD_FOLDER": str(self.root / "uploads"),
        })
        self.client = self.app.test_client()

    def tearDown(self):
        init_db.ROOT, init_db.DB_FILE = self.old_root, self.old_db
        self.temp.cleanup()

    def login(self, username, password):
        return self.client.post("/login", data={"username": username, "password": password})

    def token_login(self, username, password):
        response = self.client.post("/login", json={"username": username, "password": password})
        self.assertEqual(response.status_code, 200)
        self.api_token = response.json["token"]
        return response

    def api_get(self, path):
        return self.client.get(path, headers={"Authorization": f"Bearer {self.api_token}"})

    def counts(self):
        conn = sqlite3.connect(init_db.DB_FILE)
        try:
            return (
                conn.execute("SELECT count(*) FROM materials").fetchone()[0],
                conn.execute("SELECT count(*) FROM knowledge_entries").fetchone()[0],
            )
        finally:
            conn.close()

    def test_health_and_unauthorized(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"status": "ok"})
        self.assertEqual(self.client.get("/materials").status_code, 302)
        self.assertEqual(self.client.get("/api/materials").status_code, 401)

    def test_login_cookie_and_session(self):
        self.assertEqual(type(self.app.session_interface).__name__, "SecureCookieSessionInterface")
        bad = self.login("teacher_a", "incorrect")
        self.assertEqual(bad.status_code, 401)
        self.assertEqual(self.client.get("/api/materials").status_code, 401)
        response = self.login("teacher_a", "Teacher123!")
        self.assertEqual(response.status_code, 302)
        cookie = response.headers["Set-Cookie"]
        self.assertIn("session=", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        with self.client.session_transaction() as session:
            self.assertEqual(session["role"], "teacher")
            self.assertEqual(session["class_id"], "A")
            self.assertIsInstance(session["user_id"], int)
        html = self.client.get("/materials").get_data(as_text=True)
        self.assertIn("teacher_a", html)
        self.assertIn("A班演示材料", html)
        self.client.post("/logout")
        self.assertEqual(self.client.get("/api/materials").status_code, 401)

    def test_json_login_success_and_failure(self):
        failed = self.client.post("/login", json={"username": "teacher_a", "password": "incorrect"})
        self.assertEqual(failed.status_code, 401)
        self.assertEqual(failed.json, {"error": "用户名或密码错误"})
        self.assertEqual(self.client.get("/api/materials").status_code, 401)

        response = self.client.post("/login", json={"username": "teacher_a", "password": "Teacher123!"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/json")
        self.assertEqual({key: response.json[key] for key in ("username", "role", "class_id")}, {"username": "teacher_a", "role": "teacher", "class_id": "A"})
        self.assertEqual(len(response.json["token"].split(".")), 3)
        cookie = response.headers["Set-Cookie"]
        self.assertIn("session=", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        with self.client.session_transaction() as current_session:
            self.assertIsInstance(current_session["user_id"], int)
            self.assertEqual(current_session["role"], "teacher")
            self.assertEqual(current_session["class_id"], "A")
        self.assertEqual(self.client.get("/materials").status_code, 200)

    def test_bearer_token_login_and_materials(self):
        bad = self.client.post("/api/token/login", json={"username": "student_a1", "password": "wrong"})
        self.assertEqual(bad.status_code, 401)
        self.assertEqual(bad.json, {"error": "用户名或密码错误"})

        response = self.client.post("/api/token/login", json={"username": "student_a1", "password": "Student123!"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["token_type"], "Bearer")
        self.assertEqual(response.json["role"], "student")
        self.assertEqual(response.json["class_id"], "A")
        self.assertIn("session=", response.headers["Set-Cookie"])
        token = response.json["access_token"]
        self.assertEqual(len(token.split(".")), 3)

        # A fresh client proves bearer authorization works without a cookie.
        token_only = self.app.test_client()
        headers = {"Authorization": f"Bearer {token}"}
        materials = token_only.get("/api/materials?class_id=B", headers=headers)
        self.assertEqual(materials.status_code, 200)
        self.assertEqual(materials.json["current_user"]["username"], "student_a1")
        self.assertTrue(all(item["class_id"] == "A" for item in materials.json["materials"]))
        connection = sqlite3.connect(init_db.DB_FILE)
        try:
            b_id = connection.execute("SELECT id FROM materials WHERE class_id='B'").fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(token_only.get(f"/api/materials/{b_id}", headers=headers).status_code, 404)

        self.assertEqual(token_only.get("/api/materials", headers={"Authorization": f"Bearer {token}tampered"}).status_code, 401)
        self.assertEqual(token_only.get("/api/materials", headers={"Authorization": "Bearer"}).status_code, 401)
        # A bad bearer header must not silently fall back to a valid cookie.
        self.assertEqual(self.client.get("/api/materials", headers={"Authorization": "Bearer invalid"}).status_code, 401)

    def test_secret_key_is_required(self):
        with patch.dict(os.environ, {"SECRET_KEY": ""}):
            with self.assertRaisesRegex(RuntimeError, "SECRET_KEY"):
                create_app()

    def test_student_a1_login(self):
        response = self.login("student_a1", "Student123!")
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as current_session:
            self.assertEqual(current_session["role"], "student")
            self.assertEqual(current_session["class_id"], "A")
        self.assertIn("student_a1", self.client.get("/materials").get_data(as_text=True))

    def test_seed_users_store_hash_only(self):
        connection = sqlite3.connect(init_db.DB_FILE)
        try:
            users = connection.execute("SELECT username, password_hash FROM users ORDER BY username").fetchall()
            columns = [row[1] for row in connection.execute("PRAGMA table_info(users)")]
        finally:
            connection.close()
        self.assertEqual({user[0] for user in users}, {"teacher_a", "student_a1", "student_b1"})
        self.assertIn("password_hash", columns)
        self.assertNotIn("password", columns)
        self.assertTrue(all(user[1] not in {"Teacher123!", "Student123!"} for user in users))

    def test_class_isolation_and_query_tampering(self):
        self.token_login("student_a1", "Student123!")
        response = self.api_get("/api/materials?class_id=B")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["current_user"]["class_id"], "A")
        self.assertIn("A班演示材料", str(response.json))
        self.assertNotIn("B班演示材料", str(response.json))
        conn = sqlite3.connect(init_db.DB_FILE)
        try:
            b_id = conn.execute("SELECT id FROM materials WHERE class_id='B'").fetchone()[0]
        finally:
            conn.close()
        detail = self.api_get(f"/api/materials/{b_id}")
        self.assertEqual(detail.status_code, 404)
        self.assertNotIn("B班", detail.get_data(as_text=True))
        self.assertEqual(self.client.get(f"/materials/{b_id}/download").status_code, 404)

        self.client.post("/logout")
        self.token_login("teacher_a", "Teacher123!")
        self.assertEqual(self.api_get(f"/api/materials/{b_id}").status_code, 404)
        self.assertEqual(self.client.get(f"/materials/{b_id}/download").status_code, 404)
        self.client.post("/logout")
        self.token_login("student_b1", "Student123!")
        b_items = self.api_get("/api/materials").json["materials"]
        self.assertEqual([item["title"] for item in b_items], ["B班演示材料"])

    def test_student_upload_forbidden_without_side_effects(self):
        self.login("student_a1", "Student123!")
        before = self.counts()
        response = self.client.post("/materials/upload", data={"class_id": "B", "file": (io.BytesIO(b"hello"), "test.md")})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.counts(), before)
        self.assertEqual(list((self.root / "uploads" / "A").glob("*_test.md")), [])

    def test_teacher_upload_and_parse_failure(self):
        self.token_login("teacher_a", "Teacher123!")
        before = self.counts()
        response = self.client.post("/materials/upload", data={"title": "新增 A 班资料", "class_id": "B", "file": (io.BytesIO(b"# Lesson\nHello"), "lesson.md")})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.counts(), (before[0] + 1, before[1] + 1))
        conn = sqlite3.connect(init_db.DB_FILE)
        try:
            material = conn.execute("SELECT class_id, stored_path FROM materials WHERE title=?", ("新增 A 班资料",)).fetchone()
            knowledge = conn.execute("SELECT class_id, content FROM knowledge_entries ORDER BY id DESC LIMIT 1").fetchone()
        finally:
            conn.close()
        self.assertEqual(material[0], "A")
        self.assertEqual(knowledge, ("A", "# Lesson\nHello"))
        self.assertTrue((self.root / "uploads" / material[1]).is_file())
        self.assertIn("新增 A 班资料", str(self.api_get("/api/materials").json))

        bad = self.client.post("/materials/upload", data={"file": (io.BytesIO(b"\xff\xfe"), "bad.md")})
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self.counts(), (before[0] + 1, before[1] + 1))
        self.assertEqual(list((self.root / "uploads" / "A").glob("*_bad.md")), [])

        chinese = self.client.post("/materials/upload", data={"file": (io.BytesIO("中文内容".encode()), "课件.md")})
        self.assertEqual(chinese.status_code, 302)
        self.assertIn("课件", str(self.api_get("/api/materials").json))

    def test_teacher_upload_txt_and_pdf_rejected(self):
        self.login("teacher_a", "Teacher123!")
        before = self.counts()
        text = self.client.post("/materials/upload", data={"title": "TXT 材料", "file": (io.BytesIO(b"plain text"), "notes.txt")})
        self.assertEqual(text.status_code, 302)
        self.assertEqual(self.counts(), (before[0] + 1, before[1] + 1))
        pdf = self.client.post("/materials/upload", data={"file": (io.BytesIO(b"%PDF-fake"), "notes.pdf")})
        self.assertEqual(pdf.status_code, 400)
        self.assertEqual(self.counts(), (before[0] + 1, before[1] + 1))
        self.assertEqual(list((self.root / "uploads" / "A").glob("*_notes.pdf")), [])

    def test_teacher_download_own_class_and_deny_other_class(self):
        self.login("teacher_a", "Teacher123!")
        connection = sqlite3.connect(init_db.DB_FILE)
        try:
            a_id = connection.execute("SELECT id FROM materials WHERE class_id='A'").fetchone()[0]
            b_id = connection.execute("SELECT id FROM materials WHERE class_id='B'").fetchone()[0]
        finally:
            connection.close()
        allowed = self.client.get(f"/materials/{a_id}/download")
        forbidden = self.client.get(f"/materials/{b_id}/download")
        self.assertEqual(allowed.status_code, 200)
        self.assertIn("A班演示材料", allowed.get_data(as_text=True))
        allowed.close()
        self.assertEqual(forbidden.status_code, 404)
        self.assertNotIn("B班", forbidden.get_data(as_text=True))

    def test_token_required_expiry_and_database_class(self):
        response = self.token_login("student_a1", "Student123!")
        self.assertEqual(self.client.get("/api/materials").status_code, 401)
        self.assertEqual(self.api_get("/api/materials").status_code, 200)
        self.assertEqual(self.client.get("/api/materials", headers={"Authorization": "Bearer bad"}).status_code, 401)
        from app.tokens import _signing_key
        with self.app.app_context():
            expired = jwt.encode({
                "sub": "2", "jti": "expired-test-token",
                "iat": datetime.now(timezone.utc) - timedelta(hours=2),
                "exp": datetime.now(timezone.utc) - timedelta(hours=1),
            }, _signing_key(), algorithm="HS256")
        self.assertEqual(self.client.get("/api/materials", headers={"Authorization": f"Bearer {expired}"}).status_code, 401)
        connection = sqlite3.connect(init_db.DB_FILE)
        try:
            connection.execute("UPDATE users SET class_id='B' WHERE username='student_a1'")
            connection.commit()
        finally:
            connection.close()
        token = response.json["token"]
        changed = self.client.get("/api/materials", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.json["current_user"]["class_id"], "B")
        self.assertTrue(all(item["class_id"] == "B" for item in changed.json["materials"]))

    def test_chunk_upload_and_backfill(self):
        self.login("teacher_a", "Teacher123!")
        body = "磁铁能吸引铁钉，不能吸引木块。" * 70
        response = self.client.post("/materials/upload", data={"file": (io.BytesIO(body.encode()), "科学.md")})
        self.assertEqual(response.status_code, 302)
        connection = sqlite3.connect(init_db.DB_FILE)
        try:
            material_id = connection.execute("SELECT id FROM materials WHERE original_filename='科学.md'").fetchone()[0]
            chunks = connection.execute("SELECT chunk_index, start_offset, end_offset, content FROM knowledge_chunks WHERE material_id=? ORDER BY chunk_index", (material_id,)).fetchall()
            self.assertGreater(len(chunks), 1)
            self.assertEqual(chunks[0][:3], (0, 0, 800))
            self.assertEqual(chunks[1][1], 720)
            self.assertTrue(all(body[start:end] == text for _, start, end, text in chunks))
            connection.execute("DELETE FROM knowledge_chunks WHERE material_id=?", (material_id,))
            connection.commit()
        finally:
            connection.close()
        init_db.init_database()
        connection = sqlite3.connect(init_db.DB_FILE)
        try:
            restored = connection.execute("SELECT count(*) FROM knowledge_chunks WHERE material_id=?", (material_id,)).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(restored, len(chunks))

    def test_search_class_scope_top_four_and_no_hit(self):
        self.token_login("student_a1", "Student123!")
        connection = sqlite3.connect(init_db.DB_FILE)
        try:
            for index in range(6):
                content = f"磁铁能吸引铁钉，不能吸引木块。第 {index} 次实验。"
                cursor = connection.execute("INSERT INTO materials (title,class_id,original_filename,stored_path) VALUES (?,?,?,?)", (f"科学{index}", "A", f"科学{index}.md", f"A/test{index}.md"))
                connection.execute("INSERT INTO knowledge_entries (material_id,class_id,content) VALUES (?,?,?)", (cursor.lastrowid, "A", content))
            connection.commit()
        finally:
            connection.close()
        init_db.init_database()

        def fake_embed(text):
            if "磁铁" in text or "木块" in text:
                return [1.0, 0.0, 0.0]
            if "演示材料" in text:
                return [0.0, 1.0, 0.0]
            return [0.0, 0.0, 1.0]

        with patch("app.hybrid_search.embed_text", side_effect=fake_embed):
            forged = self.client.post("/api/knowledge/search?class_id=B", json={"query": "磁铁能吸木块吗？"}, headers={"Authorization": f"Bearer {self.api_token}"})
            self.assertEqual((forged.status_code, forged.json["results"]), (200, []))
            found = self.client.post("/api/knowledge/search", json={"query": "磁铁能吸木块吗？"}, headers={"Authorization": f"Bearer {self.api_token}"})
            self.assertEqual(found.status_code, 200)
            self.assertEqual(len(found.json["results"]), 4)
            self.assertTrue(all(item["title"].startswith("科学") for item in found.json["results"]))
            self.assertEqual([item["rank"] for item in found.json["results"]], [1, 2, 3, 4])
            missing = self.client.post("/api/knowledge/search", json={"query": "火星轨道引力"}, headers={"Authorization": f"Bearer {self.api_token}"})
            self.assertEqual(missing.json["results"], [])
        self.assertEqual(self.client.post("/api/knowledge/search", json={"query": "磁铁"}).status_code, 401)
        self.assertEqual(self.client.post("/api/knowledge/ask", json={"question": "磁铁"}).status_code, 401)
        self.token_login("student_b1", "Student123!")
        with patch("app.hybrid_search.embed_text", side_effect=fake_embed):
            b_found = self.client.post("/api/knowledge/search", json={"query": "B班演示材料"}, headers={"Authorization": f"Bearer {self.api_token}"})
        self.assertEqual(b_found.status_code, 200)
        self.assertTrue(all("B班" in item["title"] for item in b_found.json["results"]))

    def test_ask_only_calls_model_on_hit_and_citations_align(self):
        self.token_login("student_a1", "Student123!")
        headers = {"Authorization": f"Bearer {self.api_token}"}
        contexts = [{"rank": 1, "title": "小学科学课程资料.md", "chunk_index": 0,
                     "start_offset": 0, "end_offset": 20, "score": 0.8,
                     "content": "磁铁能吸引铁钉，不能吸引木块。"}]
        with patch("app.knowledge_api.search", return_value=[]), patch("app.ai.generate_answer") as model:
            no_hit = self.client.post("/api/knowledge/ask", json={"question": "火星轨道引力"}, headers=headers)
            self.assertEqual(no_hit.json, {"answer": "本班资料中没有找到相关内容。", "sources": []})
            model.assert_not_called()
        with patch("app.knowledge_api.search", return_value=contexts), patch("app.ai.generate_answer", return_value="磁铁不能吸引木块。[1]") as model:
            hit = self.client.post("/api/knowledge/ask", json={"question": "磁铁能吸木块吗？"}, headers=headers)
            self.assertEqual(hit.status_code, 200)
            self.assertEqual(hit.json["answer"], "磁铁不能吸引木块。[1]")
            self.assertEqual([source["id"] for source in hit.json["sources"]], [1])
            model.assert_called_once()


if __name__ == "__main__":
    unittest.main()
