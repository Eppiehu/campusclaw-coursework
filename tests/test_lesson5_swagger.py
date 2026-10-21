from tests.support import Fixture


class SwaggerTests(Fixture):
    def test_documents_real_routes_security_and_local_assets(self):
        specification = self.client.get("/openapi.json")
        self.assertEqual(specification.status_code, 200)
        paths = specification.json["paths"]
        expected = {"/api/login", "/api/logout", "/api/me", "/api/materials", "/api/search", "/api/ask",
                    "/api/skills", "/api/agents", "/api/conversations", "/api/conversations/{conversation_id}/messages"}
        self.assertTrue(expected <= set(paths))
        for path, operations in paths.items():
            if "login" not in path:
                for operation in operations.values():
                    self.assertEqual(operation["security"], [{"BearerAuth": []}])
        streaming = paths["/api/conversations/{conversation_id}/messages"]["post"]
        self.assertIn("text/event-stream", streaming["responses"]["200"]["content"])
        self.assertEqual(self.client.get("/swagger").status_code, 200)
        asset = self.client.get("/swagger-assets/swagger-ui-bundle.js")
        self.assertEqual(asset.status_code, 200)
        asset.close()
        # Exercise a Try-it-out equivalent using the documented URL and Bearer scheme.
        token = self.client.post("/api/login", json={"username": "student_a1", "password": "Student123!"}).json["token"]
        response = self.client.get("/api/me", headers={"Authorization": "Bearer " + token})
        self.assertEqual((response.status_code, response.json["user"]["class_id"]), (200, "A"))
