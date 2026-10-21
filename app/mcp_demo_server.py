"""Separate stdio MCP process exposing two bounded, read-only classroom tools."""
import ast
from datetime import datetime, timedelta, timezone
import json
import math
import operator
import sys

VERSION = "2025-06-18"
TOOLS = [
    {"name": "calculator", "description": "计算四则运算表达式，不执行代码。",
     "inputSchema": {"type": "object", "properties": {"expression": {"type": "string", "maxLength": 80}},
                     "required": ["expression"], "additionalProperties": False},
     "annotations": {"readOnlyHint": True, "destructiveHint": False}},
    {"name": "current_time", "description": "获取当前北京时间（Asia/Shanghai）。",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
     "annotations": {"readOnlyHint": True, "destructiveHint": False}},
]
OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
       ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod}


def calculate(expression):
    if not isinstance(expression, str) or not expression or len(expression) > 80:
        raise ValueError("表达式长度须为1至80字符")
    def evaluate(node, depth=0):
        if depth > 16:
            raise ValueError("表达式嵌套过深")
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            value = node.value
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = evaluate(node.operand, depth + 1) * (-1 if isinstance(node.op, ast.USub) else 1)
        elif isinstance(node, ast.BinOp) and type(node.op) in OPS:
            value = OPS[type(node.op)](evaluate(node.left, depth + 1), evaluate(node.right, depth + 1))
        else:
            raise ValueError("只支持数字与四则运算")
        if not math.isfinite(value) or abs(value) > 1e12:
            raise ValueError("计算结果超出范围")
        return value
    return evaluate(ast.parse(expression, mode="eval").body)


def handle(message, initialized):
    method, params = message.get("method"), message.get("params", {})
    if method == "initialize":
        return {"protocolVersion": VERSION, "capabilities": {"tools": {}},
                "serverInfo": {"name": "campusclaw-classroom-tools", "version": "1.0"}}
    if method == "ping":
        return {}
    if not initialized:
        raise ValueError("MCP尚未初始化")
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        try:
            name, args = params.get("name"), params.get("arguments", {})
            if not isinstance(args, dict):
                raise ValueError("参数必须为对象")
            if name == "calculator" and set(args) == {"expression"}:
                text = str(calculate(args["expression"]))
            elif name == "current_time" and not args:
                text = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
            else:
                raise ValueError("工具或参数无效")
            return {"content": [{"type": "text", "text": text}], "isError": False}
        except (ValueError, SyntaxError, ArithmeticError):
            return {"content": [{"type": "text", "text": "参数无效或计算失败"}], "isError": True}
    raise LookupError("不支持的方法")


def main():
    initialized = False
    for line in sys.stdin.buffer:
        if len(line) > 131072:
            return
        message = None
        try:
            message = json.loads(line)
            if "id" not in message:
                if message.get("method") == "notifications/initialized":
                    initialized = True
                continue
            result = handle(message, initialized)
            response = {"jsonrpc": "2.0", "id": message["id"], "result": result}
        except Exception:
            response = {"jsonrpc": "2.0", "id": message.get("id") if isinstance(message, dict) else None,
                        "error": {"code": -32602, "message": "无效请求"}}
        sys.stdout.buffer.write((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))
        sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
