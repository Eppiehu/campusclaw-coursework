from tests.support import Fixture

class AgentCase(Fixture):
    def test_update_disable_and_delete(self):
        headers=self.login()
        identifier=self.client.post('/api/agents',json={'name':'可编辑'},headers=headers).json['agent']['id']
        updated=self.client.put(f'/api/agents/{identifier}',json={'name':'已编辑','prompt':'','enabled':False},headers=headers)
        self.assertEqual((updated.status_code,updated.json['agent']['enabled']),(200,False))
        self.assertEqual(self.client.delete(f'/api/agents/{identifier}',headers=headers).status_code,200)
        with self.db() as db:self.assertIsNone(db.execute('SELECT id FROM tutor_agents WHERE id=?',(identifier,)).fetchone())
