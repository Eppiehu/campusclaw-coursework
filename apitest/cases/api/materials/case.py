import io
from tests.support import Fixture

class MaterialsCase(Fixture):
    def test_materials_auth_and_class_scope(self):
        headers=self.login('student_a1')
        self.assertEqual(self.client.get('/api/materials').status_code,401)
        response=self.client.get('/api/materials?class_id=B',headers=headers)
        self.assertTrue(all(row['class_id']=='A' for row in response.json['materials']))
        self.assertEqual(self.client.post('/api/materials/upload',data={'file':(io.BytesIO(b'x'),'x.txt')},headers=headers).status_code,403)
