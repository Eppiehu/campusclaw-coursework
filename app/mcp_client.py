"""Bounded MCP stdio client. Commands are administrator config, never user input."""
import copy
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time
from flask import Blueprint, current_app, jsonify
from jsonschema import Draft202012Validator
from .api_docs import api_doc
from .auth import login_required

bp = Blueprint("mcp_tools", __name__)


def observe(name, data):
    """An internal test hook; no trace UI, public endpoint, or production logging."""
    sink = current_app.config.get("LLM_OBSERVER")
    if callable(sink):
        sink(name, copy.deepcopy(data))


def allowed_tools():
    return {value.strip() for value in current_app.config["MCP_ALLOWED_TOOLS"] if value.strip()}


class MCPSession:
    def __init__(self, observer=None):
        raw = current_app.config.get("MCP_SERVER_COMMAND")
        self.command = json.loads(raw) if raw else [sys.executable, "-u", str(Path(__file__).with_name("mcp_demo_server.py"))]
        if not isinstance(self.command, list) or not self.command or any(not isinstance(part, str) or not part for part in self.command):
            raise ValueError("MCP_SERVER_COMMAND须为命令参数JSON数组")
        self.observer = observer or observe
        self.process = None
        self.inbox = queue.Queue(maxsize=32)
        self.serial = 0
        self.tools = {}
        self.allowlist = allowed_tools()

    def _read(self):
        try:
            while True:
                line = self.process.stdout.readline(131073)
                if not line or len(line) > 131072:
                    break
                self.inbox.put(json.loads(line), timeout=1)
        except Exception:
            pass
        finally:
            try:
                self.inbox.put(None, timeout=1)
            except queue.Full:
                pass

    def send(self, message):
        self.observer("mcp.request", message)
        self.process.stdin.write((json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8"))
        self.process.stdin.flush()

    def rpc(self, method, params):
        self.serial += 1
        identifier = self.serial
        self.send({"jsonrpc": "2.0", "id": identifier, "method": method, "params": params})
        deadline = time.monotonic() + 10
        for _ in range(64):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("MCP请求超时")
            try:
                response = self.inbox.get(timeout=remaining)
            except queue.Empty as error:
                raise RuntimeError("MCP请求超时") from error
            if not isinstance(response, dict):
                raise RuntimeError("MCP连接中断")
            self.observer("mcp.response", response)
            if "method" in response:
                if "id" in response:
                    self.send({"jsonrpc": "2.0", "id": response["id"], "error": {"code": -32601, "message": "Unsupported method"}})
                continue
            if response.get("id") != identifier:
                continue
            if response.get("jsonrpc") != "2.0" or response.get("error") or not isinstance(response.get("result"), dict):
                raise RuntimeError("MCP请求失败")
            return response["result"]
        raise RuntimeError("MCP响应数量超限")

    def __enter__(self):
        # The tool process gets no model key, DB credentials, token, or user session.
        environment = {key: value for key, value in os.environ.items()
                       if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}}
        self.process = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, env=environment, shell=False,
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        try:
            result = self.rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                             "clientInfo": {"name": "campusclaw", "version": "1.0"}})
            if result.get("protocolVersion") != "2025-06-18" or "tools" not in result.get("capabilities", {}):
                raise RuntimeError("MCP版本或工具能力不兼容")
            self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            cursor = None
            for _ in range(8):
                page = self.rpc("tools/list", {"cursor": cursor} if cursor else {})
                for tool in page.get("tools", []):
                    name = tool.get("name", "")
                    if name in self.allowlist and re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", name):
                        Draft202012Validator.check_schema(tool["inputSchema"])
                        self.tools[name] = tool
                cursor = page.get("nextCursor")
                if not cursor:
                    return self
            raise RuntimeError("MCP工具列表分页过多")
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def schemas(self, selected):
        if any(name not in self.tools for name in selected):
            raise RuntimeError("绑定的MCP工具当前不可用")
        return [{"type": "function", "function": {"name": name, "description": self.tools[name].get("description", ""),
                 "parameters": self.tools[name]["inputSchema"]}} for name in selected]

    def call(self, name, arguments):
        if name not in self.tools:
            raise ValueError("MCP工具未授权")
        Draft202012Validator(self.tools[name]["inputSchema"]).validate(arguments)
        result = self.rpc("tools/call", {"name": name, "arguments": arguments})
        if len(json.dumps(result, ensure_ascii=False)) > 8000:
            raise RuntimeError("MCP工具结果过长")
        return result

    def __exit__(self, *_args):
        if self.process:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=1)
            self.reader.join(timeout=2)
            self.process.stdout.close()


@bp.get("/api/mcp/tools")
@api_doc("发现服务器允许绑定的MCP外部工具", tags=["mcp"])
@login_required
def tools():
    try:
        with MCPSession() as client:
            return jsonify(tools=list(client.tools.values()))
    except Exception:
        current_app.logger.exception("MCP discovery failed")
        return jsonify(error="MCP工具服务暂不可用"), 503
