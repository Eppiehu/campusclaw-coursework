def parse_text(uploaded_file):
    """Parse the two text formats in the course specification as UTF-8."""
    data = uploaded_file.read()
    if not data:
        raise ValueError("文件不能为空")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("文件必须使用 UTF-8 编码") from exc
    if not text.strip():
        raise ValueError("文件内容不能为空")
    return text
