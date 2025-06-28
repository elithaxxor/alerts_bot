import types
import importlib
import sys
from pathlib import Path

import pytest

pytest.importorskip('pandas')


def test_api_metrics(monkeypatch, tmp_path):
    monitoring = importlib.import_module('crypto_screener_ai.app.monitoring')
    monitoring.API_METRICS.clear()

    # mock requests.get for backtest
    dummy_requests = types.ModuleType('requests')
    dummy_requests.get = lambda *a, **k: types.SimpleNamespace(json=lambda:{'prices': [[0, 1]]}, raise_for_status=lambda: None)
    monkeypatch.setitem(sys.modules, 'requests', dummy_requests)
    dummy_plotly = types.ModuleType('plotly')
    graph_objs = types.ModuleType('plotly.graph_objects')
    graph_objs.Figure = lambda *a, **k: types.SimpleNamespace(to_html=lambda **kw: '<html>')
    graph_objs.Scatter = object
    monkeypatch.setitem(sys.modules, 'plotly', dummy_plotly)
    monkeypatch.setitem(sys.modules, 'plotly.graph_objects', graph_objs)
    sys.modules.pop('crypto_screener_ai.app.backtest', None)
    backtest = importlib.import_module('crypto_screener_ai.app.backtest')
    prices = backtest.fetch_historical_prices('btc', days=1)
    assert prices == [1]
    assert monitoring.API_METRICS['coingecko']['count'] == 1
    assert monitoring.API_METRICS['coingecko']['failures'] == 0
    assert monitoring.API_METRICS['coingecko']['duration'] > 0

    monitoring.API_METRICS.clear()

    # mock ccxt for DataFetcher
    dummy_ccxt = types.ModuleType('ccxt')
    class DummyEx:
        def fetch_ticker(self, symbol):
            return {'last': 10}
    dummy_ccxt.binance = lambda *a, **k: DummyEx()
    monkeypatch.setitem(sys.modules, 'ccxt', dummy_ccxt)
    sys.modules.pop('trading_bot.data', None)
    from trading_bot.data import DataFetcher
    fetcher = DataFetcher('BTC/USDT')
    price = fetcher.get_current_price()
    assert price == 10
    assert monitoring.API_METRICS['binance']['count'] == 1
    assert monitoring.API_METRICS['binance']['failures'] == 0
    assert monitoring.API_METRICS['binance']['duration'] > 0


def test_social_posts_metrics(monkeypatch, tmp_path):
    from tests.test_dashboard import load_dashboard
    monitoring = importlib.import_module('crypto_screener_ai.app.monitoring')
    monitoring.API_METRICS.clear()
    mod = load_dashboard(tmp_path)
    mod.fetch_social_posts()
    assert monitoring.API_METRICS['reddit']['count'] == 1
    assert monitoring.API_METRICS['reddit']['failures'] == 0
    assert monitoring.API_METRICS['reddit']['duration'] > 0


def test_top25_metrics(monkeypatch):
    monitoring = importlib.import_module('crypto_screener_ai.app.monitoring')
    monitoring.API_METRICS.clear()
    dummy_requests = types.ModuleType('requests')
    dummy_requests.get = lambda *a, **k: types.SimpleNamespace(json=lambda:[{'symbol':'btc'},{'symbol':'eth'}], raise_for_status=lambda: None)
    monkeypatch.setitem(sys.modules, 'requests', dummy_requests)
    sys.modules.pop('crypto_screener_ai.app.run_screener', None)
    run_screener = importlib.import_module('crypto_screener_ai.app.run_screener')
    top = run_screener.fetch_top_25_volume()
    assert top == ['BTC', 'ETH']
    assert monitoring.API_METRICS['coingecko']['count'] == 1
    assert monitoring.API_METRICS['coingecko']['failures'] == 0
    assert monitoring.API_METRICS['coingecko']['duration'] > 0

