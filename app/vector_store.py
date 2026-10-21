"""Qdrant stores vectors and tenant payload; SQL remains the source of text."""
import json
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
from flask import current_app


class QdrantStore:
    def __init__(self):
        self.url = current_app.config["QDRANT_URL"].rstrip("/")
        self.collection = quote(current_app.config["QDRANT_COLLECTION"], safe="")

    def call(self, method, path, body=None):
        headers = {"Content-Type": "application/json"}
        key = current_app.config.get("QDRANT_API_KEY")
        if key:
            headers["api-key"] = key
        request = Request(self.url + path, data=json.dumps(body).encode() if body is not None else None, headers=headers, method=method)
        with urlopen(request, timeout=15) as response:
            return json.load(response)

    def ensure(self, dimensions):
        path = "/collections/" + self.collection
        try:
            data = self.call("GET", path)
            configuration = data["result"]["config"]["params"]["vectors"]
            if configuration["size"] != dimensions or configuration["distance"].lower() != "cosine":
                raise ValueError("向量维度与Qdrant集合不一致，请重建索引")
            return False
        except HTTPError as error:
            if error.code != 404:
                raise
        self.call("PUT", path, {"vectors": {"size": dimensions, "distance": "Cosine"}})
        return True

    def upsert(self, points):
        self.call("PUT", f"/collections/{self.collection}/points?wait=true", {"points": points})

    def query(self, vector, class_id, material_ids, limit):
        body = {"query": vector, "limit": limit, "score_threshold": 0.35, "with_payload": True,
                "filter": {"must": [
                    {"key": "class_id", "match": {"value": class_id}},
                    {"key": "material_id", "match": {"any": material_ids}},
                ]}}
        return self.call("POST", f"/collections/{self.collection}/points/query", body)["result"]["points"]

    def delete_material(self, class_id, material_id):
        self.call("POST", f"/collections/{self.collection}/points/delete?wait=true", {"filter": {"must": [
            {"key": "class_id", "match": {"value": class_id}},
            {"key": "material_id", "match": {"value": material_id}},
        ]}})


def get_store():
    injected = current_app.config.get("VECTOR_STORE")
    if injected is not None and current_app.testing:
        return injected
    return QdrantStore()
