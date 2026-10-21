"""Knowledge search and grounded question-answering API."""
from flask import Blueprint, current_app, g, jsonify, render_template, request

from .auth import login_required
from .hybrid_search import search
from .api_docs import api_doc, object_schema

bp = Blueprint("knowledge", __name__)


def required_text(field):
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get(field), str):
        return None
    value = data[field].strip()
    return value if 0 < len(value) <= 300 else None


@bp.get("/knowledge")
@login_required
def page():
    return render_template("knowledge.html")


@bp.post("/api/knowledge/search")
@bp.post("/api/search")
@api_doc("按班级执行keyword/vector/hybrid检索，跨班参数返回空hits", tags=["knowledge"], body=object_schema({"query": {"type": "string"}, "mode": {"type": "string", "enum": ["keyword", "vector", "hybrid"]}, "class_id": {"type": "string"}}, ["query"]))
@login_required
def search_api():
    query = required_text("query")
    if query is None:
        return jsonify(error="请输入不超过 300 字的问题"), 400
    data = request.get_json()
    supplied_class = data.get("class_id", request.args.get("class_id"))
    if supplied_class is not None and supplied_class != g.user["class_id"]:
        return jsonify(hits=[], results=[])
    mode = data.get("mode", "hybrid")
    if mode not in {"keyword", "vector", "hybrid"}:
        raise ValueError("无效检索模式")
    try:
        results = search(query, g.user["class_id"], mode=mode, limit=current_app.config["SEARCH_MAX_RESULTS"] if request.path == "/api/search" else 4)
    except Exception:
        current_app.logger.exception("Knowledge search failed")
        return jsonify(error="知识检索暂不可用"), 503
    return jsonify(results=results, hits=results)


@bp.post("/api/knowledge/ask")
@bp.post("/api/ask")
@api_doc("第4课单轮问答：无依据不调用模型", tags=["knowledge"], body=object_schema({"question": {"type": "string", "maxLength": 300}}, ["question"]))
@login_required
def ask_api():
    question = required_text("question")
    if question is None:
        return jsonify(error="请输入不超过 300 字的问题"), 400
    try:
        contexts = search(question, g.user["class_id"])
    except Exception:
        current_app.logger.exception("Knowledge search failed")
        return jsonify(error="知识检索暂不可用"), 503
    if not contexts:
        return jsonify(answer="本班资料中没有找到相关内容。", sources=[])
    from .ai import generate_answer
    try:
        answer = generate_answer(question, contexts)
    except Exception:
        current_app.logger.exception("Answer generation failed")
        return jsonify(error="AI 回答暂不可用，请稍后重试"), 503
    return jsonify(answer=answer, sources=[{"id": item["rank"], **{key: value for key, value in item.items() if key != "rank"}} for item in contexts])
