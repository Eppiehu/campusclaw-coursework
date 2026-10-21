"""Deterministic character chunks with offsets into the original material."""

import re

CHUNK_SIZE = 800
CHUNK_OVERLAP = 80


def split_chunks(content, strategy="auto", max_chars=CHUNK_SIZE, overlap_chars=CHUNK_OVERLAP):
    if strategy not in {"auto", "custom", "hierarchy"}:
        raise ValueError("切片策略必须是 auto、custom 或 hierarchy")
    if not isinstance(max_chars, int) or not 32 <= max_chars <= 800 or not isinstance(overlap_chars, int) or not 0 <= overlap_chars < max_chars:
        raise ValueError("切片长度须为32至800，重叠须小于切片长度")
    if not content:
        return []
    chunks = []
    start = 0
    while start < len(content):
        end = min(start + max_chars, len(content))
        if end < len(content) and strategy != "custom":
            pattern = r"\n(?=#{1,6} )|\n\s*\n" if strategy == "hierarchy" else r"\n\s*\n"
            boundaries = [start + m.start() for m in re.finditer(pattern, content[start:end])]
            usable = [boundary for boundary in boundaries if boundary > start + max(overlap_chars, max_chars // 2)]
            if usable:
                end = usable[-1]
        chunks.append((len(chunks), start, end, content[start:end]))
        if end == len(content):
            break
        start = max(start + 1, end - overlap_chars)
    return chunks


def insert_chunks(connection, material_id, class_id, content, strategy="auto", max_chars=CHUNK_SIZE, overlap_chars=CHUNK_OVERLAP):
    connection.executemany(
        """INSERT INTO knowledge_chunks
           (material_id, class_id, chunk_index, start_offset, end_offset, content, strategy)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [(material_id, class_id, index, start, end, text, strategy)
         for index, start, end, text in split_chunks(content, strategy, max_chars, overlap_chars)],
    )


def backfill_chunks(connection):
    """Idempotently index every pre-existing knowledge entry."""
    rows = connection.execute(
        """SELECT e.material_id, e.class_id, e.content FROM knowledge_entries e
           WHERE NOT EXISTS (SELECT 1 FROM knowledge_chunks c WHERE c.material_id = e.material_id)"""
    ).fetchall()
    for row in rows:
        insert_chunks(connection, row["material_id"], row["class_id"], row["content"])
    return len(rows)
