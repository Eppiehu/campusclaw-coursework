"""Run the requested acceptance checks against a running localhost:8080 server.

Temporary uploaded fixtures are removed from SQLite and uploads/ afterward.
"""
import http.cookiejar
import json
import os
import sqlite3
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8080"
PREFIX = "acceptance_" + uuid.uuid4().hex[:10]
RESULTS = []


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def client():
    return build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()), NoRedirect())


def call(opener, path, method="GET", data=None, headers=None):
    request = Request(BASE + path, data=data, method=method, headers=headers or {})
    try:
        response = opener.open(request, timeout=5)
    except HTTPError as error:
        response = error
    with response:
        return response.status, response.headers, response.read()


def login(opener, username, password):
    return call(opener, "/login", "POST", urlencode({"username": username, "password": password}).encode(), {"Content-Type": "application/x-www-form-urlencoded"})


def upload(opener, title, filename, content, extra=None):
    boundary = "----CampusClaw" + uuid.uuid4().hex
    parts = []
    fields = {"title": title, **(extra or {})}
    for name, value in fields.items():
        parts.extend([f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode()])
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode())
    parts.append(content)
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    return call(opener, "/materials/upload", "POST", b"".join(parts), {"Content-Type": f"multipart/form-data; boundary={boundary}"})


def check(name, condition, detail=""):
    passed = bool(condition)
    RESULTS.append((name, passed))
    print(f"{'PASS' if passed else 'FAIL'} | {name}{' | ' + detail if detail else ''}")


@contextmanager
def database():
    conn = sqlite3.connect(ROOT / "data" / "app.db")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def main():
    teacher = client()
    student_a = client()
    student_b = client()
    anonymous = client()
    added_paths = []
    try:
        with database() as conn:
            seed_users = {row["username"] for row in conn.execute("SELECT username FROM users")}
            classes = {row["id"] for row in conn.execute("SELECT id FROM classes")}
            a_id = conn.execute("SELECT id FROM materials WHERE class_id='A' ORDER BY id LIMIT 1").fetchone()["id"]
            b_id = conn.execute("SELECT id FROM materials WHERE class_id='B' ORDER BY id LIMIT 1").fetchone()["id"]
        check("Flask/SQLite 种子账号与 A/B 班", seed_users >= {"teacher_a", "student_a1", "student_b1"} and classes >= {"A", "B"})

        status, headers, body = call(anonymous, "/health")
        check("/health 返回 200", status == 200 and json.loads(body)["status"] == "ok")
        status, headers, body = call(anonymous, "/materials")
        check("未登录访问 materials", status == 302 and headers.get("Location") == "/login")
        status, headers, body = call(anonymous, "/api/materials")
        check("未登录访问材料 API", status == 401 and b"A\xe7\x8f\xad" not in body)

        status, headers, body = login(teacher, "teacher_a", os.environ.get("DEMO_TEACHER_PASSWORD", "Teacher123!"))
        me_status, _, me_body = call(teacher, "/api/me")
        teacher_info = json.loads(me_body)["user"] if me_status == 200 else {}
        check("teacher_a 登录", status == 302 and "session=" in headers.get("Set-Cookie", "") and teacher_info.get("role") == "teacher" and teacher_info.get("class_id") == "A")

        status, headers, body = login(student_a, "student_a1", os.environ.get("DEMO_STUDENT_PASSWORD", "Student123!"))
        me_status, _, me_body = call(student_a, "/api/me")
        student_info = json.loads(me_body)["user"] if me_status == 200 else {}
        check("student_a1 登录", status == 302 and student_info.get("role") == "student" and student_info.get("class_id") == "A")
        status, _, _ = login(student_b, "student_b1", os.environ.get("DEMO_STUDENT_PASSWORD", "Student123!"))
        check("student_b1 登录", status == 302)

        status, _, body = call(student_a, "/api/materials?class_id=B")
        materials = json.loads(body)["materials"] if status == 200 else []
        check("A 班看不到 B 班材料", status == 200 and bool(materials) and all(item["class_id"] == "A" for item in materials))

        status, _, body = call(teacher, f"/materials/{a_id}/download")
        check("teacher_a 下载 A 班材料", status == 200 and "A班演示材料" in body.decode("utf-8"))
        status, _, body = call(teacher, f"/materials/{b_id}/download")
        check("teacher_a 下载 B 班材料被拒绝", status == 404 and "B班演示材料" not in body.decode("utf-8"))

        with database() as conn:
            baseline = (conn.execute("SELECT count(*) FROM materials").fetchone()[0], conn.execute("SELECT count(*) FROM knowledge_entries").fetchone()[0])
        status, _, _ = upload(student_a, PREFIX + "_student", "student.txt", b"blocked")
        with database() as conn:
            after_student = (conn.execute("SELECT count(*) FROM materials").fetchone()[0], conn.execute("SELECT count(*) FROM knowledge_entries").fetchone()[0])
        check("student_a1 上传 txt 返回 403", status == 403 and after_student == baseline and not list((ROOT / "uploads" / "A").glob("*_student.txt")))

        status_txt, _, _ = upload(teacher, PREFIX + "_txt", "acceptance.txt", b"TXT acceptance", {"class_id": "B"})
        status_md, _, _ = upload(teacher, PREFIX + "_md", "acceptance.md", b"# Markdown acceptance")
        status_pdf, _, _ = upload(teacher, PREFIX + "_pdf", "acceptance.pdf", b"%PDF-fake")
        with database() as conn:
            rows = list(conn.execute("SELECT m.id, m.title, m.class_id, m.stored_path, k.content FROM materials m JOIN knowledge_entries k ON k.material_id=m.id WHERE m.title LIKE ?", (PREFIX + "%",)))
            current_counts = (conn.execute("SELECT count(*) FROM materials").fetchone()[0], conn.execute("SELECT count(*) FROM knowledge_entries").fetchone()[0])
        added_paths = [ROOT / "uploads" / row["stored_path"] for row in rows]
        txt_rows = [row for row in rows if row["title"] == PREFIX + "_txt"]
        md_rows = [row for row in rows if row["title"] == PREFIX + "_md"]
        check("teacher_a 上传 txt", status_txt == 302 and len(txt_rows) == 1 and txt_rows[0]["class_id"] == "A" and txt_rows[0]["content"] == "TXT acceptance" and (ROOT / "uploads" / txt_rows[0]["stored_path"]).is_file())
        check("teacher_a 上传 md", status_md == 302 and len(md_rows) == 1 and md_rows[0]["class_id"] == "A" and md_rows[0]["content"] == "# Markdown acceptance" and (ROOT / "uploads" / md_rows[0]["stored_path"]).is_file())
        check("teacher_a 上传 pdf 被拒绝", status_pdf == 400 and len(rows) == 2 and current_counts == (baseline[0] + 2, baseline[1] + 2))
    finally:
        with database() as conn:
            conn.execute("DELETE FROM materials WHERE title LIKE ?", (PREFIX + "%",))
            conn.commit()
        for path in added_paths:
            path.unlink(missing_ok=True)

    failed = [name for name, passed in RESULTS if not passed]
    print(f"RESULT: {len(RESULTS) - len(failed)}/{len(RESULTS)} PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
