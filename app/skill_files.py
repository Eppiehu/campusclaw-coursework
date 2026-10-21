"""Classroom SKILL.md front matter, with legacy course-file compatibility."""
import json
import re
import yaml

FIELDS = {"名称", "适用条件", "资料", "工具", "启用"}


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in result:
            raise ValueError("技能头部字段须为不重复的字符串")
        result[key] = loader.construct_object(value_node)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def parse_front_matter(source, lines):
    try:
        end = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration as error:
        raise ValueError("缺少技能YAML头部结束标记---") from error
    try:
        headers = yaml.load("\n".join(lines[1:end]), Loader=UniqueLoader)
    except yaml.YAMLError as error:
        raise ValueError("技能YAML头部格式错误") from error
    if not isinstance(headers, dict) or set(headers) - {"name", "description"}:
        raise ValueError("技能YAML头部仅支持name、description")
    for field, maximum in (("name", 32), ("description", 2000)):
        value = headers.get(field)
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
            raise ValueError(f"{field}须为1至{maximum}字的文本")
    body = "\n".join(lines[end + 1:]).strip()
    if not body or len(body) > 2000:
        raise ValueError("技能说明正文须为1至2000字")
    return {"name": headers["name"].strip(), "trigger_text": headers["description"].strip(),
            "description": body, "tools_json": "[]", "source_text": source,
            "subject_text": "", "enabled": 1}


def parse_skill(source):
    if not isinstance(source, str) or len(source) > 8000:
        raise ValueError("技能文件不得超过8000字")
    lines = source.lstrip("\ufeff").replace("\r\n", "\n").split("\n")
    if lines[0].strip() == "---":
        return parse_front_matter(source, lines)
    headers = {}
    body_start = None
    for index, line in enumerate(lines):
        if not line.strip():
            if headers:
                body_start = index + 1
                break
            continue
        match = re.fullmatch(r"\s*([^：:]+)[：:]\s*(.*)", line)
        if not match:
            raise ValueError("技能头部须为“字段：值”，并以空行分隔正文")
        key, value = match.group(1).strip(), match.group(2).strip()
        if key not in FIELDS:
            raise ValueError(f"未定义字段：{key}")
        if key in headers:
            raise ValueError(f"重复字段：{key}")
        headers[key] = value
    for required in ("名称", "适用条件", "启用"):
        if not headers.get(required):
            raise ValueError(f"缺少必填字段：{required}")
    body = "\n".join(lines[body_start:]).strip() if body_start is not None else ""
    if not body:
        raise ValueError("缺少技能说明正文")
    for key, maximum in [("名称", 32), ("适用条件", 120), ("资料", 32)]:
        if len(headers.get(key, "")) > maximum:
            raise ValueError(f"{key}不得超过{maximum}字")
    if len(body) > 2000:
        raise ValueError("技能说明正文不得超过2000字")
    if headers["启用"] not in {"是", "否"}:
        raise ValueError("启用只能是“是”或“否”")
    tools = [part.strip() for part in re.split(r"[,，、;；|]", headers.get("工具", "")) if part.strip()]
    if any(tool != "knowledge_search" for tool in tools):
        raise ValueError("非法工具名：本课只允许knowledge_search")
    return {"name": headers["名称"], "trigger_text": headers["适用条件"], "description": body,
            "tools_json": json.dumps(list(dict.fromkeys(tools))), "source_text": source,
            "subject_text": headers.get("资料", ""), "enabled": int(headers["启用"] == "是")}


def route_skill(question, candidates):
    scored = []
    question = question.lower()
    for skill in candidates:
        words = [word.strip().lower() for word in re.split(r"[,，、;；|]", skill["trigger_text"]) if word.strip()]
        if (skill["source_text"] or "").lstrip("\ufeff").startswith("---"):
            # The standard description is prose rather than a keyword field.
            # Use deterministic description-derived bigrams; never execute file text.
            prose = skill["trigger_text"].lower()
            stop = {"用户", "需要", "使用", "支持", "进行", "可以", "帮助", "学习", "内容", "提供", "以及", "用于", "当用", "时使"}
            words = set(re.findall(r"[a-z][a-z0-9_-]+", prose))
            for phrase in re.findall(r"[\u4e00-\u9fff]+", prose):
                words.update(phrase[i:i+2] for i in range(len(phrase)-1) if phrase[i:i+2] not in stop)
        score = sum(word in question for word in words)
        if score:
            scored.append((score, skill["id"], skill))
    return min(scored, key=lambda item: (-item[0], item[1]))[2] if scored else None
