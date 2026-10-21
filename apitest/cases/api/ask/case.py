from unittest.mock import patch
from tests.support import Fixture

class AskCase(Fixture):
    def test_lesson4_no_evidence_never_calls_model(self):
        headers=self.login('student_a1')
        with patch('app.knowledge_api.search',return_value=[]),patch('app.ai.generate_answer') as model:
            response=self.client.post('/api/ask',json={'question':'无关问题'},headers=headers)
        self.assertEqual(response.json,{'answer':'本班资料中没有找到相关内容。','sources':[]})
        model.assert_not_called()
