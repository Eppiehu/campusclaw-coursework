"""Class-scoped Agent, skill-file and private conversation interfaces."""
import json
from flask import Blueprint, g, jsonify, request
from .api_docs import api_doc, object_schema
from .auth import login_required, teacher_required
from .db import get_db
from .skill_files import parse_skill

bp = Blueprint("tutors", __name__)
NOT_FOUND = {"error": "不存在"}
AGENT_BODY = object_schema({"name": {"type": "string", "maxLength": 64}, "prompt": {"type": "string", "maxLength": 2000},
                           "prompt_template_id": {"type": "integer", "nullable": True},
                           "mcp_tools": {"type": "array", "items": {"type": "string"}},
                           "enabled": {"type": "boolean"}, "skill_ids": {"type": "array", "items": {"type": "integer"}},
                           "material_ids": {"type": "array", "items": {"type": "integer"}}})


def scoped(table, identifier, enabled=False):
    sql = f"SELECT * FROM {table} WHERE id=? AND class_id=?"
    if enabled:
        sql += " AND enabled=1"
    return get_db().execute(sql, (identifier, g.user["class_id"])).fetchone()


def conversation(identifier):
    return get_db().execute("SELECT * FROM conversations WHERE id=? AND user_id=? AND class_id=?",
                            (identifier, g.user["id"], g.user["class_id"])).fetchone()


def skill_json(row):
    data = dict(row)
    data["enabled"] = bool(data["enabled"])
    data["tools"] = json.loads(data.get("tools_json") or "[]")
    return data


def read_skill_file():
    file = request.files.get("file")
    if file is None or not file.filename or not file.filename.lower().endswith((".txt", ".md")):
        raise ValueError("请上传单一UTF-8 .txt或.md技能文件")
    try:
        return parse_skill(file.read(32004).decode("utf-8-sig"))
    except UnicodeDecodeError as error:
        raise ValueError("技能文件必须使用UTF-8编码") from error


def json_object():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("需要JSON对象")
    return data


@bp.route("/api/skills", methods=["GET", "POST"])
@api_doc("列出本班技能或教师上传技能文件", tags=["skills"], multipart=True)
@login_required
def skills():
    if request.method == "GET":
        sql = "SELECT * FROM skills WHERE class_id=?"
        if g.user["role"] != "teacher":
            sql += " AND enabled=1"
        return jsonify(skills=[skill_json(row) for row in get_db().execute(sql + " ORDER BY id", (g.user["class_id"],))])
    return create_skill()


@teacher_required
def create_skill():
    data = read_skill_file()
    if get_db().execute("SELECT id FROM skills WHERE class_id=? AND name=?", (g.user["class_id"], data["name"])).fetchone():
        return jsonify(error="本班技能名称已存在"), 409
    fields = list(data)
    cursor = get_db().execute(f"INSERT INTO skills (class_id,{','.join(fields)}) VALUES ({','.join('?' for _ in range(len(fields)+1))})", [g.user["class_id"], *data.values()])
    get_db().commit()
    return jsonify(skill=skill_json(scoped("skills", cursor.lastrowid))), 201


@bp.route("/api/skills/<int:skill_id>", methods=["GET", "PUT", "PATCH", "DELETE"])
@api_doc("读取、上传替换、启停或删除本班技能", tags=["skills"], multipart=True, body=object_schema({"enabled": {"type": "boolean"}}))
@login_required
def skill_detail(skill_id):
    if request.method != "GET" and g.user["role"] != "teacher":
        return jsonify(error="仅教师可以执行此操作"), 403
    row = scoped("skills", skill_id, g.user["role"] != "teacher")
    if row is None:
        return jsonify(NOT_FOUND), 404
    connection = get_db()
    if request.method == "DELETE":
        connection.execute("DELETE FROM tutor_agent_skills WHERE skill_id=?", (skill_id,))
        connection.execute("DELETE FROM skills WHERE id=?", (skill_id,))
    elif request.method == "PUT":
        data = read_skill_file()
        if connection.execute("SELECT id FROM skills WHERE class_id=? AND name=? AND id<>?", (g.user["class_id"], data["name"], skill_id)).fetchone():
            return jsonify(error="本班技能名称已存在"), 409
        connection.execute("UPDATE skills SET " + ",".join(f"{field}=?" for field in data) + " WHERE id=?", [*data.values(), skill_id])
    elif request.method == "PATCH":
        data = json_object()
        if type(data.get("enabled")) is not bool:
            raise ValueError("enabled必须是布尔值")
        connection.execute("UPDATE skills SET enabled=? WHERE id=?", (int(data["enabled"]), skill_id))
    if request.method != "GET":
        connection.commit()
    return jsonify(status="ok") if request.method == "DELETE" else jsonify(skill=skill_json(scoped("skills", skill_id)))


def agent_json(row):
    data = dict(row)
    data["enabled"] = bool(data["enabled"])
    data["mcp_tools"] = json.loads(data.pop("mcp_tools_json", None) or "[]")
    data["skill_ids"] = [item[0] for item in get_db().execute("SELECT skill_id FROM tutor_agent_skills WHERE agent_id=? ORDER BY skill_id", (row["id"],))]
    data["material_ids"] = [item[0] for item in get_db().execute("SELECT material_id FROM tutor_agent_materials WHERE agent_id=? ORDER BY material_id", (row["id"],))]
    return data


def validate_agent(data, old=None):
    name = data.get("name", old["name"] if old else "")
    prompt = data.get("prompt", old["prompt"] if old else "")
    if prompt is None:
        prompt = ""
    enabled = data.get("enabled", bool(old["enabled"]) if old else True)
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 64:
        raise ValueError("Agent名称须为1至64字")
    if not isinstance(prompt, str) or len(prompt) > 2000:
        raise ValueError("Agent prompt不得超过2000字，可为空")
    if type(enabled) is not bool:
        raise ValueError("enabled必须是布尔值")
    data.update(name=name.strip(), prompt=prompt, enabled=int(enabled))
    if "prompt_template_id" in data and data["prompt_template_id"] is not None:
        if type(data["prompt_template_id"]) is not int:
            raise ValueError("prompt_template_id必须是整数或null")
        template = scoped("prompt_templates", data["prompt_template_id"])
        if template is None or (not template["enabled"] and (old is None or old["prompt_template_id"] != template["id"])):
            return False
    if "mcp_tools" in data:
        from .mcp_client import allowed_tools
        values = data["mcp_tools"]
        if not isinstance(values, list) or any(not isinstance(value, str) or value not in allowed_tools() for value in values):
            raise ValueError("请选择服务器允许的MCP工具")
    for field, table in [("skill_ids", "skills"), ("material_ids", "materials")]:
        if field not in data:
            continue
        if not isinstance(data[field], list) or any(type(value) is not int for value in data[field]):
            raise ValueError(f"{field}必须是整数数组")
        for identifier in data[field]:
            if scoped(table, identifier) is None:
                return False
    return True


def save_agent(data, identifier=None):
    connection = get_db()
    duplicate = connection.execute("SELECT id FROM tutor_agents WHERE class_id=? AND name=?", (g.user["class_id"], data["name"])).fetchone()
    if duplicate and duplicate[0] != identifier:
        return jsonify(error="本班Agent名称已存在"), 409
    if identifier is None:
        cursor = connection.execute("INSERT INTO tutor_agents (class_id,name,prompt,enabled) VALUES (?,?,?,?)", (g.user["class_id"], data["name"], data["prompt"], data["enabled"]))
        identifier = cursor.lastrowid
    else:
        connection.execute("UPDATE tutor_agents SET name=?,prompt=?,enabled=? WHERE id=?", (data["name"], data["prompt"], data["enabled"], identifier))
    if "prompt_template_id" in data:
        connection.execute("UPDATE tutor_agents SET prompt_template_id=? WHERE id=?", (data["prompt_template_id"], identifier))
    if "mcp_tools" in data:
        connection.execute("UPDATE tutor_agents SET mcp_tools_json=? WHERE id=?", (json.dumps(sorted(set(data["mcp_tools"]))), identifier))
    for field, table, column in [("skill_ids", "tutor_agent_skills", "skill_id"), ("material_ids", "tutor_agent_materials", "material_id")]:
        if field in data:
            connection.execute(f"DELETE FROM {table} WHERE agent_id=?", (identifier,))
            connection.executemany(f"INSERT INTO {table} (agent_id,{column}) VALUES (?,?)", [(identifier, value) for value in sorted(set(data[field]))])
    connection.commit()
    return jsonify(agent=agent_json(scoped("tutor_agents", identifier)))


@bp.route("/api/agents", methods=["GET", "POST"])
@api_doc("列出本班Agent；教师创建并绑定技能和材料", tags=["agents"], body=AGENT_BODY)
@login_required
def agents():
    if request.method == "GET":
        sql = "SELECT * FROM tutor_agents WHERE class_id=?"
        if g.user["role"] != "teacher":
            sql += " AND enabled=1"
        return jsonify(agents=[agent_json(row) for row in get_db().execute(sql + " ORDER BY id", (g.user["class_id"],))])
    return create_agent()


@teacher_required
def create_agent():
    data = json_object()
    if not validate_agent(data):
        return jsonify(NOT_FOUND), 404
    response = save_agent(data)
    return response if isinstance(response, tuple) else (response, 201)


@bp.route("/api/agents/<int:agent_id>", methods=["GET", "PUT", "PATCH", "DELETE"])
@api_doc("读取、修改绑定、启停或删除本班Agent", tags=["agents"], body=AGENT_BODY)
@login_required
def agent_detail(agent_id):
    if request.method != "GET" and g.user["role"] != "teacher":
        return jsonify(error="仅教师可以执行此操作"), 403
    row = scoped("tutor_agents", agent_id, g.user["role"] != "teacher")
    if row is None:
        return jsonify(NOT_FOUND), 404
    if request.method == "GET":
        return jsonify(agent=agent_json(row))
    if request.method == "DELETE":
        if get_db().execute("SELECT id FROM conversations WHERE agent_id=? LIMIT 1", (agent_id,)).fetchone():
            return jsonify(error="Agent已被会话锁定，请改为停用"), 409
        get_db().execute("DELETE FROM tutor_agent_skills WHERE agent_id=?", (agent_id,))
        get_db().execute("DELETE FROM tutor_agent_materials WHERE agent_id=?", (agent_id,))
        get_db().execute("DELETE FROM tutor_agents WHERE id=?", (agent_id,))
        get_db().commit()
        return jsonify(status="ok")
    data = json_object()
    if not validate_agent(data, row):
        return jsonify(NOT_FOUND), 404
    return save_agent(data, agent_id)


@bp.route("/api/conversations", methods=["GET", "POST"])
@api_doc("列出自己的会话或选择已启用Agent创建会话", tags=["conversations"], body=object_schema({"agent_id": {"type": "integer"}}, ["agent_id"]))
@login_required
def conversations():
    if request.method == "GET":
        rows = get_db().execute("SELECT * FROM conversations WHERE user_id=? AND class_id=? ORDER BY updated_at DESC,id DESC", (g.user["id"], g.user["class_id"]))
        return jsonify(conversations=[dict(row) for row in rows])
    data = json_object()
    if type(data.get("agent_id")) is not int:
        raise ValueError("必须选择Agent")
    agent = scoped("tutor_agents", data["agent_id"], enabled=True)
    if agent is None:
        return jsonify(NOT_FOUND), 404
    cursor = get_db().execute("INSERT INTO conversations (class_id,user_id,agent_id,title) VALUES (?,?,?,?)", (g.user["class_id"], g.user["id"], agent["id"], "新的提问"))
    get_db().commit()
    return jsonify(conversation=dict(conversation(cursor.lastrowid))), 201


@bp.route("/api/conversations/<int:conversation_id>", methods=["GET", "DELETE"])
@api_doc("读取或删除自己的私有会话", tags=["conversations"])
@login_required
def conversation_detail(conversation_id):
    row = conversation(conversation_id)
    if row is None:
        return jsonify(NOT_FOUND), 404
    if request.method == "DELETE":
        get_db().execute("DELETE FROM messages WHERE conversation_id=?", (conversation_id,))
        get_db().execute("DELETE FROM conversations WHERE id=?", (conversation_id,))
        get_db().commit()
        return jsonify(status="ok")
    messages = []
    for message in get_db().execute("SELECT * FROM messages WHERE conversation_id=? ORDER BY id", (conversation_id,)):
        item = dict(message)
        item["citations"] = json.loads(item.pop("citations_json") or "[]")
        messages.append(item)
    return jsonify(conversation=dict(row), messages=messages)
