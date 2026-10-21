from tests.support import Fixture

class MeCase(Fixture):
    def test_database_authority(self):
        headers=self.login('student_a1')
        with self.db() as db:db.execute("UPDATE users SET class_id='B' WHERE username='student_a1'")
        response=self.client.get('/api/me',headers=headers)
        self.assertEqual((response.status_code,response.json['user']['class_id']),(200,'B'))
