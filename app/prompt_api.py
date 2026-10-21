"""Reusable, class-scoped teacher prompt templates."""
from flask import Blueprint, g, jsonify, request
from .api_docs import api_doc, object_schema
from .auth import login_required
from .db import get_db
from .tutor_api import NOT_FOUND, json_object, scoped

bp = Blueprint("prompt_templates", __name__)
BODY = object_schema({"name": {"type": "string", "maxLength": 64},
                      "content": {"type": "string", "maxLength": 2000}, "enabled": {"type": "boolean"}})


def serialize(row):
    return {**dict(row), "enabled": bool(row["enabled"])}


def validated(data, old=None):
    result = {}
    for field, maximum in (("name", 64), ("content", 2000)):
        value = data.get(field, old[field] if old else "")
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
            raise ValueError(f"{field}须为1至{maximum}字")
        result[field] = value.strip()
    enabled = data.get("enabled", bool(old["enabled"]) if old else True)
    if type(enabled) is not bool:
        raise ValueError("enabled必须是布尔值")
    result["enabled"] = int(enabled)
    return result


@bp.route("/api/prompt-templates", methods=["GET", "POST"])
@api_doc("列出本班提示词模板；教师创建模板", tags=["prompt-templates"], body=BODY)
@login_required
def templates():
    if request.method == "GET":
        suffix = "" if g.user["role"] == "teacher" else " AND enabled=1"
        rows = get_db().execute("SELECT * FROM prompt_templates WHERE class_id=?" + suffix + " ORDER BY id", (g.user["class_id"],))
        return jsonify(templates=[serialize(row) for row in rows])
    if g.user["role"] != "teacher":
        return jsonify(error="仅教师可以执行此操作"), 403
    data = validated(json_object())
    if get_db().execute("SELECT id FROM prompt_templates WHERE class_id=? AND name=?", (g.user["class_id"], data["name"])).fetchone():
        return jsonify(error="本班模板名称已存在"), 409
    cursor = get_db().execute("INSERT INTO prompt_templates (class_id,name,content,enabled) VALUES (?,?,?,?)",
                              (g.user["class_id"], data["name"], data["content"], data["enabled"]))
    get_db().commit()
    return jsonify(template=serialize(scoped("prompt_templates", cursor.lastrowid))), 201


@bp.route("/api/prompt-templates/<int:template_id>", methods=["GET", "PUT", "PATCH", "DELETE"])
@api_doc("读取、编辑、启停或删除本班提示词模板", tags=["prompt-templates"], body=BODY)
@login_required
def detail(template_id):
    if request.method != "GET" and g.user["role"] != "teacher":
        return jsonify(error="仅教师可以执行此操作"), 403
    old = scoped("prompt_templates", template_id, g.user["role"] != "teacher")
    if old is None:
        return jsonify(NOT_FOUND), 404
    if request.method == "GET":
        return jsonify(template=serialize(old))
    if request.method == "DELETE":
        if get_db().execute("SELECT id FROM tutor_agents WHERE prompt_template_id=? LIMIT 1", (template_id,)).fetchone():
            return jsonify(error="模板已绑定助手，请先解除绑定"), 409
        get_db().execute("DELETE FROM prompt_templates WHERE id=?", (template_id,))
        get_db().commit()
        return jsonify(status="ok")
    data = validated(json_object(), old)
    if get_db().execute("SELECT id FROM prompt_templates WHERE class_id=? AND name=? AND id<>?",
                        (g.user["class_id"], data["name"], template_id)).fetchone():
        return jsonify(error="本班模板名称已存在"), 409
    get_db().execute("UPDATE prompt_templates SET name=?,content=?,enabled=? WHERE id=?",
                     (data["name"], data["content"], data["enabled"], template_id))
    get_db().commit()
    return jsonify(template=serialize(scoped("prompt_templates", template_id)))
