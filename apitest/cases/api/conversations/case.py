from tests.support import Fixture

class ConversationsCase(Fixture):
    def test_creation_needs_enabled_agent(self):
        teacher=self.login()
        agent=self.client.post('/api/agents',json={'name':'会话助手'},headers=teacher).json['agent']['id']
        student=self.login('student_a1')
        response=self.client.post('/api/conversations',json={'agent_id':agent},headers=student)
        self.assertEqual((response.status_code,response.json['conversation']['title']),(201,'新的提问'))
        with self.db() as db:self.assertEqual(db.execute('SELECT agent_id FROM conversations').fetchone()[0],agent)
