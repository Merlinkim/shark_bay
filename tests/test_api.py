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

    def test_strategy_registry(self):
        r = self.client.get('/strategies/registry')
        self.assertEqual(r.status_code, 200)
        payload = r.json()
        self.assertIn('strategies', payload)
        self.assertIsInstance(payload['strategies'], list)
        self.assertIn('strategy_name', payload['strategies'][0])

    @patch('app.api.build_snapshot')
    def test_research_features_shape(self, snapshot_mock):
        snapshot_mock.return_value = {
            'symbol': 'BTCUSDT', 'interval': '1m', 'lookback_hours': 24, 'rows_used': 30,
            'latest_open_time': '2026-01-01T00:00:00+00:00',
            'features': {'return_1m': 0.1, 'regime_label': 'trend'},
            'quality': {'status': 'ok', 'gaps_detected': 0, 'notes': []},
        }
        r = self.client.get('/research/features')
        self.assertEqual(r.status_code, 200)
        payload = r.json()
        self.assertIn('features', payload)
        self.assertIn('quality', payload)


    @patch('app.api._get_research_experiment_repo')
    def test_research_experiments_latest(self, repo_factory):
        repo_factory.return_value.list_latest.return_value = [{
            'experiment_id': 'e1', 'strategy_name': 'ema_cross_v1', 'strategy_version': 'v0',
            'symbol': 'BTCUSDT', 'interval': '1m', 'dataset_start': None, 'dataset_end': None,
            'dataset_row_count': 0, 'dataset_fingerprint': 'f', 'parameters': {}, 'features_used': [],
            'intended_regime': 'trend', 'risk_profile': 'medium', 'total_return_pct': 0.0, 'sharpe': 0.0,
            'max_drawdown_pct': 0.0, 'win_rate_pct': 0.0, 'trade_count': 0, 'status': 'real_backtest',
            'is_simulated': False, 'created_at': '2026-01-01T00:00:00+00:00',
        }]
        r = self.client.get('/research/experiments/latest')
        self.assertEqual(r.status_code, 200)
        self.assertIn('experiments', r.json())

    @patch('app.api._get_research_experiment_repo')
    def test_research_experiments_latest_empty(self, repo_factory):
        repo_factory.return_value.list_latest.return_value = []
        r = self.client.get('/research/experiments/latest')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['experiments'], [])


    @patch('app.api.get_active_symbols')
    def test_symbols_active_shape(self, active_symbols):
        active_symbols.return_value = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        r = self.client.get('/symbols/active')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['count'], 3)
        self.assertEqual(r.json()['symbols'][1], 'ETHUSDT')

    @patch('app.api._get_research_experiment_repo')
    def test_research_analytics_empty(self, repo_factory):
        repo_factory.return_value.list_latest.return_value = []
        r = self.client.get('/research/analytics')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['summary']['total_experiments'], 0)


    @patch('app.api.run_walk_forward_backtest')
    def test_research_walk_forward_endpoint(self, wf_run):
        wf_run.return_value = {'strategy_name': 'ema_cross_v1', 'window_count': 1, 'windows': [], 'aggregate': {}}
        r = self.client.get('/research/walk-forward/run', params={
            'strategy': 'ema_cross_v1',
            'symbol': 'BTCUSDT',
            'interval': '1m',
            'start': '2024-04-01T00:00:00Z',
            'end': '2025-03-31T23:59:00Z',
            'train_days': 180,
            'validation_days': 30,
            'test_days': 30,
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['strategy_name'], 'ema_cross_v1')


    @patch('app.api.run_research_agent')
    def test_research_agent_recommendations_endpoint(self, agent_run):
        agent_run.return_value = {
            'generated_at': '2026-01-01T00:00:00+00:00',
            'agent_version': 'research_agent_v0',
            'symbol': 'BTCUSDT',
            'interval': '1m',
            'research_summary': {},
            'overfit_risk': {'label': 'low', 'flags': []},
            'strategy_assessments': [],
            'recommended_experiments': [],
            'rejected_strategies': [],
            'next_actions': [],
            'safety': {'order_execution_enabled': False},
        }
        r = self.client.get('/research/agent/recommendations', params={'symbol':'BTCUSDT','interval':'1m'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['agent_version'], 'research_agent_v0')


    @patch('app.api.psycopg.connect')
    def test_ingestion_telemetry_shape(self, connect_mock):
        conn = connect_mock.return_value.__enter__.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchone.side_effect = [
            {'reconnect_count': 2},
            {'latest_candle_timestamp': None, 'upsert_total': 0},
        ]
        with patch('app.api._configured_symbols', return_value=['BTCUSDT']):
            r = self.client.get('/ingestion/telemetry')
        self.assertEqual(r.status_code, 200)
        payload = r.json()
        self.assertIn('symbols', payload)
        self.assertIn('symbol_metrics', payload)
        self.assertIn('BTCUSDT', payload['symbol_metrics'])



    @patch('app.api.get_strategy_registry_metadata')
    @patch('app.api._get_backtest_job_repo')
    def test_create_backtest_job(self, repo_factory, metadata_mock):
        metadata_mock.return_value = {'sma_crossover': {'version': 'v1'}}
        repo_factory.return_value.create_job.return_value = '11111111-1111-1111-1111-111111111111'
        r = self.client.post('/research/jobs/backtest', json={
            'strategy_id': 'sma_crossover',
            'params': {'short_window': 5, 'long_window': 20},
            'risk_config': {'max_drawdown': 0.2},
            'execution_config': {'initial_cash': 10000},
            'candle_query': {'symbol': 'BTCUSDT', 'interval': '1m'}
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['status'], 'queued')

    @patch('app.api._get_backtest_job_repo')
    def test_get_backtest_job_status(self, repo_factory):
        repo_factory.return_value.get_job.return_value = {
            'id': '11111111-1111-1111-1111-111111111111',
            'status': 'running',
            'created_at': '2026-01-01T00:00:00Z',
            'started_at': '2026-01-01T00:01:00Z',
            'finished_at': None,
            'cancel_requested': False,
            'error_message': None,
        }
        r = self.client.get('/research/jobs/11111111-1111-1111-1111-111111111111')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['status'], 'running')

    @patch('app.api._get_backtest_job_repo')
    def test_cancel_backtest_job(self, repo_factory):
        repo = repo_factory.return_value
        repo.get_job.side_effect = [
            {'id': '11111111-1111-1111-1111-111111111111', 'status': 'running'},
            {'id': '11111111-1111-1111-1111-111111111111', 'status': 'running', 'cancel_requested': True},
        ]
        r = self.client.post('/research/jobs/11111111-1111-1111-1111-111111111111/cancel')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['cancel_requested'])

    @patch('app.api._get_backtest_job_repo')
    def test_get_backtest_job_result(self, repo_factory):
        repo = repo_factory.return_value
        repo.get_job.return_value = {
            'id': '11111111-1111-1111-1111-111111111111',
            'status': 'success',
        }
        repo.get_job_result.return_value = {
            'result': {'summary_metrics': {'total_return': 1.23}},
            'result_reference': 'backtest_results/BTCUSDT/1m/result-123',
        }
        r = self.client.get('/research/jobs/11111111-1111-1111-1111-111111111111/result')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['status'], 'success')
        self.assertEqual(r.json()['result']['summary_metrics']['total_return'], 1.23)


    @patch('app.api._get_research_review_repo')
    def test_create_research_review(self, repo_factory):
        repo_factory.return_value.create.return_value = {
            'id': 'r1', 'strategy_id': 'bb_rsi_reversion', 'experiment_run_id': 'exp-run-1', 'run_id': 'run-1',
            'job_id': 'job-1', 'verdict': 'candidate', 'risk_level': 'medium', 'overfit_risk': 'low',
            'summary': 'looks promising', 'failure_reasons_json': [], 'required_changes_json': [],
            'recommendation_to_arthur': 'monitor', 'created_by_agent': 'lancelot', 'created_at': '2026-01-01T00:00:00+00:00'
        }
        r = self.client.post('/research/reviews', json={
            'strategy_id': 'bb_rsi_reversion',
            'experiment_run_id': 'exp-run-1',
            'run_id': 'run-1',
            'job_id': 'job-1',
            'verdict': 'candidate',
            'risk_level': 'medium',
            'overfit_risk': 'low',
            'summary': 'looks promising',
            'failure_reasons': [],
            'required_changes': [],
            'recommendation_to_arthur': 'monitor',
            'created_by_agent': 'lancelot',
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['id'], 'r1')

    @patch('app.api._get_strategy_lifecycle_repo')
    def test_create_strategy_proposal(self, repo_factory):
        repo_factory.return_value.create_proposal.return_value = {
            'strategy_id': 's1',
            'title': 'Mean Reversion',
            'description': 'test',
            'current_status': 'idea',
            'created_by_agent': 'arthur',
            'created_at': '2026-01-01T00:00:00+00:00',
            'updated_at': '2026-01-01T00:00:00+00:00',
        }
        r = self.client.post('/research/strategies/proposals', json={
            'strategy_id': 's1',
            'title': 'Mean Reversion',
            'description': 'test',
            'created_by_agent': 'arthur',
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['current_status'], 'idea')

    @patch('app.api._get_strategy_lifecycle_repo')
    def test_get_strategy_proposal(self, repo_factory):
        repo_factory.return_value.get_strategy.return_value = {
            'strategy_id': 's1',
            'title': 'Mean Reversion',
            'description': 'test',
            'current_status': 'idea',
            'created_by_agent': 'arthur',
            'created_at': '2026-01-01T00:00:00+00:00',
            'updated_at': '2026-01-01T00:00:00+00:00',
        }
        r = self.client.get('/research/strategies/s1')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['strategy_id'], 's1')

    @patch('app.api._get_strategy_lifecycle_repo')
    def test_patch_strategy_status(self, repo_factory):
        repo_factory.return_value.patch_status.return_value = {
            'strategy_id': 's1',
            'title': 'Mean Reversion',
            'description': 'test',
            'current_status': 'backtested',
            'created_by_agent': 'arthur',
            'created_at': '2026-01-01T00:00:00+00:00',
            'updated_at': '2026-01-01T01:00:00+00:00',
        }
        r = self.client.patch('/research/strategies/s1/status', json={
            'to_status': 'backtested',
            'reason': 'Backtest complete',
            'changed_by_agent': 'lancelot',
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['current_status'], 'backtested')

    def test_patch_strategy_status_invalid(self):
        r = self.client.patch('/research/strategies/s1/status', json={
            'to_status': 'live',
            'reason': 'invalid',
            'changed_by_agent': 'lancelot',
        })
        self.assertEqual(r.status_code, 422)

    @patch('app.api._get_strategy_lifecycle_repo')
    def test_get_strategy_history(self, repo_factory):
        repo_factory.return_value.get_history.return_value = [
            {
                'strategy_id': 's1',
                'from_status': 'idea',
                'to_status': 'hypothesis',
                'reason': 'refined',
                'changed_by_agent': 'arthur',
                'created_at': '2026-01-01T00:10:00+00:00',
            }
        ]
        r = self.client.get('/research/strategies/s1/history')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()[0]['to_status'], 'hypothesis')

    @patch('app.api._get_research_review_repo')
    def test_list_research_reviews(self, repo_factory):
        repo_factory.return_value.list.return_value = [{
            'id': 'r1', 'strategy_id': 'bb_rsi_reversion', 'experiment_run_id': 'exp-run-1', 'run_id': 'run-1',
            'job_id': 'job-1', 'verdict': 'candidate', 'risk_level': 'medium', 'overfit_risk': 'low',
            'summary': 'ok', 'failure_reasons_json': [], 'required_changes_json': [],
            'recommendation_to_arthur': '', 'created_by_agent': 'lancelot', 'created_at': '2026-01-01T00:00:00+00:00'
        }]
        r = self.client.get('/research/reviews', params={'strategy_id': 'bb_rsi_reversion'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 1)

    def test_create_research_review_invalid_verdict(self):
        r = self.client.post('/research/reviews', json={
            'strategy_id': 'bb_rsi_reversion',
            'experiment_run_id': 'exp-run-1',
            'run_id': 'run-1',
            'job_id': 'job-1',
            'verdict': 'ship_it',
            'risk_level': 'medium',
            'overfit_risk': 'low',
            'summary': 'bad',
            'created_by_agent': 'lancelot',
        })
        self.assertEqual(r.status_code, 422)

if __name__ == '__main__':
    unittest.main()
