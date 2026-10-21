"""OpenAPI is derived from Flask's registered routes and handler annotations."""
from pathlib import Path
import re
from flask import Blueprint, current_app, jsonify, render_template_string, send_from_directory

bp = Blueprint("openapi", __name__)


@bp.get("/openapi.json")
def specification():
    paths = {}
    for rule in sorted(current_app.url_map.iter_rules(), key=lambda item: item.rule):
        view = current_app.view_functions[rule.endpoint]
        doc = getattr(view, "api_documentation", None)
        if doc is None or (not rule.rule.startswith("/api/") and rule.rule not in {"/login", "/logout"}):
            continue
        path = re.sub(r"<(?:(?:int|string):)?([^>]+)>", r"{\1}", rule.rule)
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            if method == "GET" and rule.rule == "/login":
                continue
            operation = {"summary": doc["summary"], "tags": doc["tags"],
                         "operationId": rule.endpoint.replace(".", "_") + "_" + method.lower() + "_" + re.sub(r"\W", "_", rule.rule),
                         "security": [{"BearerAuth": []}] if doc["auth"] else [],
                         "responses": {"200": {"description": "成功"}, "201": {"description": "创建成功"}, "400": {"description": "输入错误"},
                                       "401": {"description": "Token无效或已吊销"}, "403": {"description": "需要教师身份"},
                                       "404": {"description": "不存在（包含不可见资源）"}, "409": {"description": "名称冲突或资源已被会话引用"}, "503": {"description": "依赖服务不可用"}}}
            parameters = []
            for name in sorted(rule.arguments):
                parameters.append({"name": name, "in": "path", "required": True, "schema": {"type": "integer"}})
            if parameters:
                operation["parameters"] = parameters
            if method in {"POST", "PUT", "PATCH"}:
                if doc["multipart"] and method in {"POST", "PUT"}:
                    schema = {"type": "object", "properties": {"file": {"type": "string", "format": "binary"},
                              "title": {"type": "string"}, "strategy": {"type": "string", "enum": ["auto", "custom", "hierarchy"]},
                              "max_chars": {"type": "integer", "default": 800}, "overlap_chars": {"type": "integer", "default": 80}}, "required": ["file"]}
                    content_type = "multipart/form-data"
                else:
                    schema = doc["body"] or {"type": "object"}
                    content_type = "application/json"
                operation["requestBody"] = {"required": bool(schema.get("required")), "content": {content_type: {"schema": schema}}}
            if doc["stream"]:
                operation["responses"]["200"]["content"] = {"text/event-stream": {"schema": {"type": "string"}}}
                operation["description"] = "首帧meta；delta.text为新增片段；assistant落库后done；首帧后失败为error事件。"
            paths.setdefault(path, {})[method.lower()] = operation
    return jsonify(openapi="3.0.3", info={"title": "CampusClaw 第5课 API", "version": "5.0"}, paths=paths,
                   components={"securitySchemes": {"BearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}}})


@bp.get("/swagger-assets/<path:filename>")
def assets(filename):
    from swagger_ui_bundle import swagger_ui_path
    return send_from_directory(swagger_ui_path, filename)


@bp.get("/swagger")
def swagger():
    return render_template_string('''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>CampusClaw Swagger</title>
    <link rel="stylesheet" href="/swagger-assets/swagger-ui.css"></head><body><div id="swagger-ui"></div>
    <script src="/swagger-assets/swagger-ui-bundle.js"></script><script>SwaggerUIBundle({url:'/openapi.json',dom_id:'#swagger-ui',persistAuthorization:true});</script></body></html>''')
