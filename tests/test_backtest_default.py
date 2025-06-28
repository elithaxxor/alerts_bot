import importlib
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_run_backtest_default(monkeypatch):
    dummy_requests = types.ModuleType('requests')
    dummy_requests.get = lambda *a, **k: types.SimpleNamespace(json=lambda: {'prices': [[0,1],[1,2]]}, raise_for_status=lambda: None)
    monkeypatch.setitem(sys.modules, 'requests', dummy_requests)

    dummy_plotly = types.ModuleType('plotly')
    graph_objs = types.ModuleType('plotly.graph_objects')
    graph_objs.Figure = lambda *a, **k: types.SimpleNamespace(to_html=lambda **kw: '<html>')
    graph_objs.Scatter = lambda *a, **k: object()
    dummy_plotly.graph_objects = graph_objs
    monkeypatch.setitem(sys.modules, 'plotly', dummy_plotly)
    monkeypatch.setitem(sys.modules, 'plotly.graph_objects', graph_objs)

    sys.modules.pop('crypto_screener_ai.app.backtest', None)
    backtest = importlib.import_module('crypto_screener_ai.app.backtest')

    monkeypatch.setattr(backtest, 'fetch_historical_prices', lambda symbol, days=90: [1,2,3,4,5])

    result = backtest.run_backtest('btc')
    assert result['symbol'] == 'BTC'
    assert 'chart_html' in result
    assert 'return_pct' in result
