import unittest

from app.strategy_registry import list_strategy_specs


class TestStrategyRegistry(unittest.TestCase):
    def test_expected_strategies_exist(self):
        names = {s['strategy_name'] for s in list_strategy_specs()}
        self.assertTrue({'sma_crossover', 'bb_rsi_reversion'}.issubset(names))

    def test_no_duplicate_strategy_names(self):
        strategies = list_strategy_specs()
        names = [s['strategy_name'] for s in strategies]
        self.assertEqual(len(names), len(set(names)))


if __name__ == '__main__':
    unittest.main()
