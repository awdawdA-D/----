import unittest
from app import create_app

class SmokeTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_index_ok(self):
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        self.assertIn('框架已运行'.encode('utf-8'), res.data)

if __name__ == '__main__':
    unittest.main()
