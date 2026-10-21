from tests.support import Fixture

class AgentsCase(Fixture):
    def test_enabled_list(self):
        teacher=self.login()
        for name,enabled in [('助手一',True),('助手二',False)]:
            self.assertEqual(self.client.post('/api/agents',json={'name':name,'enabled':enabled},headers=teacher).status_code,201)
        student=self.login('student_a1')
        response=self.client.get('/api/agents',headers=student)
        self.assertEqual([row['name'] for row in response.json['agents']],['助手一'])
