from tests.support import Fixture

class LogoutCase(Fixture):
    def test_logout_persists_revocation(self):
        headers=self.login('student_a1')
        self.assertEqual(self.client.post('/api/logout',json={},headers=headers).status_code,200)
        self.assertEqual(self.client.get('/api/me',headers=headers).status_code,401)
        with self.db() as db:self.assertEqual(db.execute('SELECT count(*) FROM token_revocations').fetchone()[0],1)
