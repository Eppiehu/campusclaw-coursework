import jwt
from tests.support import Fixture

class LoginCase(Fixture):
    def test_login_payload_and_db_user(self):
        response = self.client.post('/api/login',json={'username':'student_a1','password':'Student123!'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(set(jwt.decode(response.json['token'],options={'verify_signature':False})),{'sub','jti','iat','exp'})
        self.assertEqual(response.json['class_id'],'A')
        self.assertIn('HttpOnly',response.headers['Set-Cookie'])
        self.assertEqual(self.client.post('/api/login',json={'username':'student_a1','password':'bad'}).status_code,401)
