import uuid
from pathlib import Path

from flask import Blueprint, current_app, g, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.utils import secure_filename

from .auth import login_required
from .db import get_db
from .knowledge import parse_text

bp = Blueprint("materials", __name__)


def list_materials():
    return get_db().execute(
        "SELECT id, title, class_id, original_filename, created_at FROM materials WHERE class_id = ? ORDER BY id DESC",
        (session["class_id"],),
    ).fetchall()


def get_material(material_id):
    return get_db().execute(
        "SELECT id, title, class_id, original_filename, stored_path, created_at FROM materials WHERE id = ? AND class_id = ?",
        (material_id, session["class_id"]),
    ).fetchone()


@bp.get("/materials")
@login_required
def list_page():
    materials = list_materials()
    selected = materials[0] if materials else None
    content = None
    if selected:
        row = get_db().execute("SELECT content FROM knowledge_entries WHERE material_id = ?", (selected["id"],)).fetchone()
        content = row["content"] if row else ""
    return render_template("materials.html", materials=materials, selected=selected, content=content)


@bp.get("/api/materials")
@login_required
def list_api():
    return jsonify(materials=[dict(item) for item in list_materials()], current_user=dict(g.user))


@bp.get("/api/materials/<int:material_id>")
@login_required
def detail_api(material_id):
    material = get_material(material_id)
    if material is None:
        return jsonify(error="材料不存在"), 404
    entry = get_db().execute("SELECT content FROM knowledge_entries WHERE material_id = ?", (material_id,)).fetchone()
    return jsonify(material={key: material[key] for key in ("id", "title", "class_id", "original_filename", "created_at")}, content=entry["content"] if entry else "")


@bp.get("/materials/<int:material_id>/download")
@login_required
def download(material_id):
    material = get_material(material_id)
    if material is None:
        return "材料不存在", 404
    file_path = Path(current_app.config["UPLOAD_FOLDER"]) / material["stored_path"]
    if not file_path.is_file():
        return "材料文件不存在", 404
    return send_file(file_path, as_attachment=True, download_name=material["original_filename"])


@bp.post("/materials/upload")
@login_required
def upload():
    if g.user["role"] != "teacher":
        return "仅教师可以上传材料", 403
    file = request.files.get("file")
    if file is None or not file.filename:
        return "请选择文件", 400
    original_name = file.filename.replace("\\", "/").split("/")[-1]
    extension = Path(original_name).suffix.lower()
    if extension not in {".txt", ".md"}:
        return "仅支持 .txt 和 .md 文件", 400
    safe_stem = (secure_filename(Path(original_name).stem) or "material")[:80]
    filename = f"{safe_stem}{extension}"
    title = request.form.get("title", "").strip() or Path(original_name).stem
    if len(title) > 120:
        return "标题过长", 400

    class_id = session["class_id"]
    relative = Path(class_id) / f"{uuid.uuid4().hex}_{filename}"
    destination = Path(current_app.config["UPLOAD_FOLDER"]) / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    connection = get_db()
    try:
        file.save(destination)
        with destination.open("rb") as saved:
            content = parse_text(saved)
        connection.execute("BEGIN")
        cursor = connection.execute(
            "INSERT INTO materials (title, class_id, uploaded_by, original_filename, stored_path) VALUES (?, ?, ?, ?, ?)",
            (title, class_id, g.user["id"], original_name, relative.as_posix()),
        )
        connection.execute(
            "INSERT INTO knowledge_entries (material_id, class_id, content) VALUES (?, ?, ?)",
            (cursor.lastrowid, class_id, content),
        )
        connection.commit()
    except ValueError as exc:
        connection.rollback()
        destination.unlink(missing_ok=True)
        return str(exc), 400
    except Exception:
        connection.rollback()
        destination.unlink(missing_ok=True)
        current_app.logger.exception("Material upload failed")
        return "上传失败", 500
    return redirect(url_for("materials.list_page"))
