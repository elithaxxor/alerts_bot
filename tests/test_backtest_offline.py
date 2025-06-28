import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import importlib
import types


def test_fetch_historical_prices_offline(tmp_path, monkeypatch):
    dummy_requests = types.ModuleType('requests')
    def get(*args, **kwargs):
        raise AssertionError('network should not be called')
    dummy_requests.get = get
    monkeypatch.setitem(sys.modules, 'requests', dummy_requests)

    cache = Path('data/hist_btc.json')
    cache.write_text(json.dumps([1, 2, 3]))
    monkeypatch.setenv('OFFLINE_MODE', '1')

    backtest = importlib.import_module('crypto_screener_ai.app.backtest')
    prices = backtest.fetch_historical_prices('btc', 3)
    assert prices == [1, 2, 3]
    cache.unlink()

