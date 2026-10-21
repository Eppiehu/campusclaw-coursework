"""Operation annotations live on the actual Flask handlers."""


def api_doc(summary, *, body=None, auth=True, tags=None, stream=False, multipart=False):
    def decorate(function):
        function.api_documentation = {"summary": summary, "body": body, "auth": auth,
                                      "tags": tags or [], "stream": stream, "multipart": multipart}
        return function
    return decorate


def object_schema(properties, required=()):
    return {"type": "object", "properties": properties, "required": list(required)}
