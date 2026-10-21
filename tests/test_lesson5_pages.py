from tests.support import Fixture


class PageTests(Fixture):
    def test_pages_and_session_fallback(self):
        anonymous = self.client.get("/tutor")
        self.assertEqual((anonymous.status_code, anonymous.headers["Location"]), (302, "/login"))
        self.login("student_a1")
        self.assertEqual(self.client.get("/tutor").status_code, 200)
        self.assertEqual(self.client.get("/manage").status_code, 403)
        self.login()
        management = self.client.get("/manage")
        self.assertEqual(management.status_code, 200)
        self.assertIn('type="file"', management.get_data(as_text=True))
        page = self.client.get("/materials").get_data(as_text=True)
        self.assertIn('action="/materials/upload"', page)
        self.assertIn('action="/logout"', page)
        self.assertIn('href="/tutor"', page)
