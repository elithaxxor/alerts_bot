import importlib
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_load_strategy(tmp_path):
    dummy_requests = types.ModuleType('requests')
    dummy_requests.get = lambda *a, **k: types.SimpleNamespace(json=lambda: {'prices': [[0,1],[1,2],[2,3]]}, raise_for_status=lambda: None)
    sys.modules['requests'] = dummy_requests

    dummy_plotly = types.ModuleType('plotly')
    graph_objs = types.ModuleType('plotly.graph_objects')
    graph_objs.Figure = lambda *a, **k: types.SimpleNamespace(to_html=lambda **kw: '<html>')
    graph_objs.Scatter = lambda *a, **k: object()
    dummy_plotly.graph_objects = graph_objs
    sys.modules['plotly'] = dummy_plotly
    sys.modules['plotly.graph_objects'] = graph_objs

    sys.modules.pop('crypto_screener_ai.app.backtest', None)
    mod = importlib.import_module('crypto_screener_ai.app.backtest')
    # create dummy strategy file
    strat_file = tmp_path / 'dummy.py'
    strat_file.write_text('''class Strategy:\n    def run(self, prices):\n        return {"trades": 0, "return_pct": 1.23}''')
    # temporarily add to strategies path
    orig = Path(mod.__file__).resolve().parents[2] / 'strategies'
    orig.mkdir(exist_ok=True)
    target = orig / 'dummy.py'
    target.write_text(strat_file.read_text())
    try:
        result = mod.run_backtest('btc', days=1, strategy='dummy')
        assert result['return_pct'] == 1.23
        assert 'chart_html' in result
    finally:
        target.unlink()

