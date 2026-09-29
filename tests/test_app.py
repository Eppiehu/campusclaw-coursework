import io
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import create_app
from scripts import init_db


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
        self.assertEqual(response.json, {"username": "teacher_a", "role": "teacher", "class_id": "A"})
        cookie = response.headers["Set-Cookie"]
        self.assertIn("session=", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        with self.client.session_transaction() as current_session:
            self.assertIsInstance(current_session["user_id"], int)
            self.assertEqual(current_session["role"], "teacher")
            self.assertEqual(current_session["class_id"], "A")
        self.assertEqual(self.client.get("/materials").status_code, 200)

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
        self.login("student_a1", "Student123!")
        response = self.client.get("/api/materials?class_id=B")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["current_user"]["class_id"], "A")
        self.assertIn("A班演示材料", str(response.json))
        self.assertNotIn("B班演示材料", str(response.json))
        conn = sqlite3.connect(init_db.DB_FILE)
        try:
            b_id = conn.execute("SELECT id FROM materials WHERE class_id='B'").fetchone()[0]
        finally:
            conn.close()
        detail = self.client.get(f"/api/materials/{b_id}")
        self.assertEqual(detail.status_code, 404)
        self.assertNotIn("B班", detail.get_data(as_text=True))
        self.assertEqual(self.client.get(f"/materials/{b_id}/download").status_code, 404)

        self.client.post("/logout")
        self.login("teacher_a", "Teacher123!")
        self.assertEqual(self.client.get(f"/api/materials/{b_id}").status_code, 404)
        self.assertEqual(self.client.get(f"/materials/{b_id}/download").status_code, 404)
        self.client.post("/logout")
        self.login("student_b1", "Student123!")
        b_items = self.client.get("/api/materials").json["materials"]
        self.assertEqual([item["title"] for item in b_items], ["B班演示材料"])

    def test_student_upload_forbidden_without_side_effects(self):
        self.login("student_a1", "Student123!")
        before = self.counts()
        response = self.client.post("/materials/upload", data={"class_id": "B", "file": (io.BytesIO(b"hello"), "test.md")})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.counts(), before)
        self.assertEqual(list((self.root / "uploads" / "A").glob("*_test.md")), [])

    def test_teacher_upload_and_parse_failure(self):
        self.login("teacher_a", "Teacher123!")
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
        self.assertIn("新增 A 班资料", str(self.client.get("/api/materials").json))

        bad = self.client.post("/materials/upload", data={"file": (io.BytesIO(b"\xff\xfe"), "bad.md")})
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self.counts(), (before[0] + 1, before[1] + 1))
        self.assertEqual(list((self.root / "uploads" / "A").glob("*_bad.md")), [])

        chinese = self.client.post("/materials/upload", data={"file": (io.BytesIO("中文内容".encode()), "课件.md")})
        self.assertEqual(chinese.status_code, 302)
        self.assertIn("课件", str(self.client.get("/api/materials").json))

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


if __name__ == "__main__":
    unittest.main()
