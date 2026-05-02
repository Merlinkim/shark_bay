import unittest
from fastapi.testclient import TestClient

from app.api import app


class TestAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health(self):
        r = self.client.get('/health')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['status'], 'OK')

    def test_candles_limit_validation(self):
        r = self.client.get('/candles', params={'symbol': 'BTCUSDT', 'interval': '1m', 'limit': 0})
        self.assertEqual(r.status_code, 422)


if __name__ == '__main__':
    unittest.main()
