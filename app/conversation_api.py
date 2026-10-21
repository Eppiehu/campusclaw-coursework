import json
from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context
from .api_docs import api_doc, object_schema
from .auth import login_required
from .chat_stream import OutputBoundary, require_configuration, stream_model
from .conversation_flow import HiddenResource, build_messages, prepare_turn, save_assistant
from .tutor_api import NOT_FOUND
from .mcp_client import MCPSession, observe

bp = Blueprint("conversation_stream", __name__)


def agent_stream(turn, messages):
    selected = json.loads(turn["agent"].get("mcp_tools_json") or "[]")
    if selected:
        with MCPSession() as client:
            yield from stream_model(messages, tools=client.schemas(selected), call_tool=client.call)
    else:
        yield from stream_model(messages)


def event(name, data):
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@bp.post("/api/conversations/<int:conversation_id>/messages")
@api_doc("向锁定Agent提问；POST SSE按meta/delta/done或error返回", tags=["conversations"], stream=True,
         body=object_schema({"question": {"type": "string", "maxLength": 500}, "agent_id": {"type": "integer", "description": "会话已锁定，此字段不会更换Agent"}}, ["question"]))
@login_required
def send_message(conversation_id):
    data = request.get_json(silent=True)
    question = data.get("question") if isinstance(data, dict) else None
    if not isinstance(question, str) or not question.strip() or len(question.strip()) > 500:
        return jsonify(error="问题须为1至500字"), 400
    provider = current_app.config.get("CHAT_STREAM_FACTORY") if current_app.testing else None
    try:
        turn = prepare_turn(conversation_id, question.strip())
        if provider is None:
            require_configuration()
    except HiddenResource:
        return jsonify(NOT_FOUND), 404
    except Exception:
        current_app.logger.exception("Conversation preparation failed")
        return jsonify(error="会话服务暂不可用"), 503

    @stream_with_context
    def generate():
        # 8: metadata is always the first event; no model content precedes it.
        yield event("meta", {"status": "ok", "skill": turn["skill"]["name"] if turn["skill"] else None, "citations": turn["citations"]})
        parts = []
        boundary = OutputBoundary(turn)
        saved = False
        try:
            # 9: bounded history + system/current user. 10: true upstream stream.
            messages = build_messages(turn)
            observe("flow.context", {"agent_id": turn["agent"]["id"], "skill": turn["skill"],
                                      "citations": turn["citations"], "messages": messages})
            upstream = provider(messages) if provider else agent_stream(turn, messages)
            for text in upstream:
                for piece in boundary.feed(text):
                    parts.append(piece)
                    yield event("delta", {"text": piece})
            for piece in boundary.feed("", final=True):
                parts.append(piece)
                yield event("delta", {"text": piece})
            if not parts:
                raise RuntimeError("模型未返回正文")
            # 11: commit assistant/citations/skill first, then emit done.
            identifier = save_assistant(turn, "".join(parts))
            saved = True
            yield event("done", {"message_id": identifier})
        except GeneratorExit:
            raise
        except Exception:
            current_app.logger.exception("Conversation stream interrupted")
            for piece in boundary.feed("", final=True):
                parts.append(piece)
                yield event("delta", {"text": piece})
            identifier = None
            if parts and not saved:
                try:
                    identifier = save_assistant(turn, "".join(parts))
                    saved = True
                except Exception:
                    current_app.logger.exception("Partial answer persistence failed")
            yield event("error", {"error": "生成中断，已生成内容已保留" if saved else "生成失败", "message_id": identifier})
        finally:
            if parts and not saved:
                try:
                    save_assistant(turn, "".join(parts))
                except Exception:
                    current_app.logger.exception("Disconnected stream persistence failed")

    return Response(generate(), content_type="text/event-stream; charset=utf-8", headers={
        "X-Accel-Buffering": "no", "Cache-Control": "no-cache", "Connection": "keep-alive",
    })
