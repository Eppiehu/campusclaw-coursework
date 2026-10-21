"""True upstream OpenAI-compatible SSE, with bounded output checks."""
import json
import os
import re
import copy
from urllib.request import Request, urlopen


def require_configuration():
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("未配置聊天模型密钥")


def stream_model(messages, tools=None, call_tool=None):
    from .mcp_client import observe
    require_configuration()
    messages = copy.deepcopy(messages)
    available = {tool["function"]["name"] for tool in tools or []}
    for round_index in range(3):
        body = {"model": os.environ.get("CHAT_MODEL") or "deepseek-flash", "messages": messages,
                "stream": True, "temperature": 0.1, "max_tokens": 600}
        if tools:
            body.update(tools=tools, tool_choice="auto" if round_index < 2 else "none")
        request = Request((os.environ.get("OPENAI_BASE_URL") or "https://api.deepseek.com").rstrip("/") + "/chat/completions",
                          data=json.dumps(body, ensure_ascii=False).encode(), method="POST",
                          headers={"Content-Type": "application/json", "Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]})
        observe("llm.request", {"url": request.full_url, "body": body})
        calls, content, ended = {}, [], False
        with urlopen(request, timeout=120) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    ended = True
                    break
                event = json.loads(data)
                observe("llm.response", event)
                if event.get("error"):
                    raise RuntimeError("上游模型生成失败")
                choices = event.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                text = delta.get("content")
                if isinstance(text, str) and text:
                    content.append(text)
                    yield text
                for fragment in delta.get("tool_calls") or []:
                    index = fragment.get("index")
                    if type(index) is not int or index not in range(4):
                        raise RuntimeError("模型工具调用数量超限")
                    target = calls.setdefault(index, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                    target["id"] += fragment.get("id", "")
                    function = fragment.get("function") or {}
                    target["function"]["name"] += function.get("name", "")
                    target["function"]["arguments"] += function.get("arguments", "")
                    if len(target["function"]["arguments"]) > 4096 or len(target["id"]) > 128 or len(target["function"]["name"]) > 64:
                        raise RuntimeError("模型工具调用参数过长")
        if not ended:
            raise RuntimeError("模型流提前中断")
        if not calls:
            return
        if round_index == 2 or call_tool is None:
            raise RuntimeError("模型工具调用轮数超限或未绑定工具")
        ordered = [calls[key] for key in sorted(calls)]
        if len({call["id"] for call in ordered}) != len(ordered):
            raise RuntimeError("模型工具调用编号重复")
        messages.append({"role": "assistant", "content": "".join(content) or None, "tool_calls": ordered})
        for call in ordered:
            name = call["function"]["name"]
            if name not in available or not call["id"]:
                raise RuntimeError("模型请求了未绑定工具")
            arguments = json.loads(call["function"]["arguments"])
            if not isinstance(arguments, dict):
                raise RuntimeError("工具参数须为对象")
            result = call_tool(name, arguments)
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result, ensure_ascii=False)})


class OutputBoundary:
    """One sentence/128 chars of lookahead, never a full-completion playback."""
    def __init__(self, turn):
        self.buffer = ""
        self.citation_count = len(turn["citations"])
        self.guidance = bool(turn["skill"] and "解题引导" in turn["skill"]["name"])
        self.replaced = False
        self.tail = ""

    def clean(self, text):
        text = re.sub(r"\[(\d+)\]", lambda match: match.group(0) if 1 <= int(match.group(1)) <= self.citation_count else "", text)
        if not self.citation_count and re.search(r"资料.{0,8}(?:未找到|没有找到|无相关)", text):
            text = "我可以先帮你分析问题。请补充你的思路或卡住的步骤，我再给出下一步建议。"
        if self.guidance:
            check = re.sub(r"第[\d一二三四五六七八九十]+步", "", text)
            check = re.sub(r"\[\d+\]", "", check)
            if re.search(r"最终答案|选项|得数|完整解题过程|答案(?:是|为)|结果(?:是|为)|(?:选|选择)[A-DＡ-Ｄ]|\d|\b[A-D]\b", check):
                if self.replaced:
                    return ""
                self.replaced = True
                hint = "先检查你上一处推理或变形是否满足题目条件；下一步核对该步骤的依据，并告诉我你卡住的位置。"
                return hint + ("[1]" if self.citation_count else "")
        return text

    def feed(self, text, final=False):
        self.buffer += text
        pieces = []
        while self.buffer:
            match = re.search(r"[。！？\n]", self.buffer)
            if match:
                end = match.end()
            elif len(self.buffer) >= 128:
                end = 128
                # Avoid breaking an unfinished citation across the boundary.
                bracket = self.buffer.rfind("[", 0, end)
                if bracket >= 0 and "]" not in self.buffer[bracket:end]:
                    end = bracket or end
            elif final:
                end = len(self.buffer)
            else:
                break
            clean = self.clean(self.buffer[:end])
            self.buffer = self.buffer[end:]
            clean = re.sub(r"(\[\d+\])(?:\s*\1)+", r"\1", clean)
            prefix = re.match(r"\[\d+\]", clean)
            if prefix and self.tail.rstrip().endswith(prefix.group(0)):
                clean = clean[prefix.end():]
            self.tail = (self.tail + clean)[-32:]
            pieces.extend(clean[index:index + 16] for index in range(0, len(clean), 16))
        return pieces
