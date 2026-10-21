"""Class-filtered TF-IDF plus semantic cosine search over SQLite chunks."""
from collections import Counter
import math
import re
from flask import current_app

from .db import get_db
from .embeddings import embed_text
from .vector_store import get_store

TOP_K = 4
RRF_K = 60


def terms(text):
    """Keep English words and overlapping Chinese bigrams for short questions."""
    result = re.findall(r"[a-z0-9]+|[\u3400-\u9fff]+", text.lower())
    tokens = []
    for part in result:
        if "\u3400" <= part[0] <= "\u9fff":
            tokens.extend(part[i:i + 2] for i in range(max(1, len(part) - 1)))
        else:
            tokens.append(part)
    return tokens


def cosine(left, right):
    if len(left) != len(right) or not left:
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    denominator = math.sqrt(sum(a * a for a in left) * sum(b * b for b in right))
    return max(0.0, min(1.0, numerator / denominator)) if denominator else 0.0


def lexical_scores(query, texts):
    vectors = [Counter(terms(text)) for text in [query, *texts]]
    document_count = max(1, len(texts))
    frequencies = Counter(token for vector in vectors[1:] for token in vector)
    weights = {token: math.log(1 + (document_count + 1) / (count + 1))
               for token, count in frequencies.items()}

    def weighted(vector):
        return {key: (1 + math.log(value)) * weights.get(key, 0.0)
                for key, value in vector.items()}

    query_vector = weighted(vectors[0])
    return [cosine_sparse(query_vector, weighted(vector)) for vector in vectors[1:]]


def cosine_sparse(left, right):
    dot = sum(value * right.get(key, 0.0) for key, value in left.items())
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


def search(query, class_id, mode="hybrid", material_ids=None, subject_text="", limit=TOP_K):
    if mode not in {"keyword", "vector", "hybrid"}:
        raise ValueError("检索模式必须为keyword、vector或hybrid")
    if material_ids is not None and not material_ids:
        return []
    connection = get_db()
    sql = (
        """SELECT c.id, c.chunk_index, c.start_offset, c.end_offset, c.content,
                  c.status, c.material_id, m.title
           FROM knowledge_chunks c JOIN materials m ON m.id = c.material_id
           WHERE c.class_id = ? AND m.class_id = ?"""
    )
    params = [class_id, class_id]
    if material_ids is not None:
        sql += " AND m.id IN (" + ",".join("?" for _ in material_ids) + ")"
        params.extend(material_ids)
    rows = connection.execute(sql + " ORDER BY c.id", params).fetchall()
    rows = [row for row in rows if row["content"].strip() and (not subject_text or subject_text.lower() in row["title"].lower())]
    if not rows:
        return []

    maximum = current_app.config["SEARCH_MAX_RESULTS"]
    by_id = {row["id"]: row for row in rows}
    keyword = []
    vector_hits = []
    if mode in {"keyword", "hybrid"}:
        scores = lexical_scores(query, [row["content"] for row in rows])
        keyword = sorted([(row["id"], score) for row, score in zip(rows, scores) if score > 0], key=lambda hit: (-hit[1], hit[0]))[:maximum]
    if mode in {"vector", "hybrid"}:
        query_vector = embed_text(query)
        store = get_store()
        created = store.ensure(len(query_vector))
        pending = [row for row in rows if created or row["status"] != "ready"]
        if pending:
            store.upsert([{"id": row["id"], "vector": embed_text(row["content"]), "payload": {
                "class_id": class_id, "material_id": row["material_id"], "chunk_index": row["chunk_index"],
            }} for row in pending])
            connection.executemany("UPDATE knowledge_chunks SET status='ready' WHERE id=? AND class_id=?", [(row["id"], class_id) for row in pending])
            connection.commit()
        points = store.query(query_vector, class_id, sorted({row["material_id"] for row in rows}), maximum)
        vector_hits = [(point["id"], point["score"]) for point in points if point["id"] in by_id and point["score"] >= 0.35][:maximum]
    if mode == "hybrid":
        fused = {}
        for ranking in (keyword, vector_hits):
            for rank, (chunk_id, _) in enumerate(ranking, 1):
                fused[chunk_id] = fused.get(chunk_id, 0.0) + 1 / (RRF_K + rank)
        scored = sorted(fused.items(), key=lambda hit: (-hit[1], hit[0]))
    else:
        scored = keyword if mode == "keyword" else vector_hits
    return [
        {
            "rank": rank, "chunk_id": row["id"], "material_id": row["material_id"],
            "title": row["title"],
            "chunk_index": row["chunk_index"],
            "start_offset": row["start_offset"],
            "end_offset": row["end_offset"],
            "score": round(score, 6),
            "content": row["content"],
        }
        for rank, (chunk_id, score) in enumerate(scored[:limit], start=1)
        for row in [by_id[chunk_id]]
    ]
