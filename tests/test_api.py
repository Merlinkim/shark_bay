import unittest
from unittest.mock import patch
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

    @patch('app.api._get_backtest_repo')
    def test_backtests_list(self, repo_factory):
        repo = repo_factory.return_value
        repo.list_runs.return_value = [
            {
                'run_id': '11111111-1111-1111-1111-111111111111',
                'status': 'completed',
                'symbol': 'BTCUSDT',
                'interval': '1m',
                'start_time': None,
                'end_time': None,
                'config_hash': 'abc123',
                'dataset_fingerprint': 'fp123',
                'created_at': '2026-01-01T00:00:00Z',
            }
        ]
        r = self.client.get('/backtests')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()[0]['run_id'], '11111111-1111-1111-1111-111111111111')

    @patch('app.api._get_backtest_repo')
    def test_backtest_not_found(self, repo_factory):
        repo = repo_factory.return_value
        repo.get_run_with_metrics.return_value = None
        r = self.client.get('/backtests/11111111-1111-1111-1111-111111111111')
        self.assertEqual(r.status_code, 404)

    @patch('app.api._get_backtest_repo')
    def test_backtest_run_id_validation(self, repo_factory):
        r = self.client.get('/backtests/not-a-uuid')
        self.assertEqual(r.status_code, 422)
        repo_factory.assert_not_called()

    @patch('app.api._get_backtest_repo')
    def test_backtest_fills_ordered(self, repo_factory):
        repo = repo_factory.return_value
        repo.get_run_with_metrics.return_value = {'run_id': '11111111-1111-1111-1111-111111111111'}
        repo.get_fills.return_value = [
            {'fill_index': 0, 'open_time': '2026-01-01T00:00:00Z', 'prev_position': 0, 'new_position': 1, 'exec_price': 100.0}
        ]
        r = self.client.get('/backtests/11111111-1111-1111-1111-111111111111/fills')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()[0]['fill_index'], 0)

    @patch('app.api._get_backtest_repo')
    def test_backtest_equity_curve_ordered(self, repo_factory):
        repo = repo_factory.return_value
        repo.get_run_with_metrics.return_value = {'run_id': '11111111-1111-1111-1111-111111111111'}
        repo.get_equity_curve.return_value = [
            {'point_index': 0, 'open_time': '2026-01-01T00:00:00Z', 'equity': 10000.0}
        ]
        r = self.client.get('/backtests/11111111-1111-1111-1111-111111111111/equity-curve')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()[0]['point_index'], 0)


if __name__ == '__main__':
    unittest.main()
