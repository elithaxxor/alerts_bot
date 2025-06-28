import sys
import types
import importlib
import json
from pathlib import Path

class DummyHTTPException(Exception):
    def __init__(self, status_code=500, detail=None):
        self.status_code = status_code
        self.detail = detail

def load_dashboard(tmp_path):
    # mock requests
    dummy_requests = types.ModuleType('requests')
    def post(url, *a, **k):
        return types.SimpleNamespace(status_code=200)
    def get(url, *a, **k):
        if 'coingecko' in url:
            return types.SimpleNamespace(json=lambda:{'btc':{'usd':100},'eth':{'usd':50}}, status_code=200)
        return types.SimpleNamespace(json=lambda:{}, status_code=200)
    dummy_requests.get = get
    dummy_requests.post = post
    sys.modules['requests'] = dummy_requests

    # mock ccxt
    dummy_ccxt = types.ModuleType('ccxt')
    class DummyExchange:
        def fetch_order_book(self, symbol, limit=20):
            return {'bids': [[1,2]], 'asks': [[1.1,3]]}
    dummy_ccxt.binance = lambda *a, **k: DummyExchange()
    sys.modules['ccxt'] = dummy_ccxt

    # mock plotly
    dummy_plotly = types.ModuleType('plotly')
    graph_objs = types.ModuleType('plotly.graph_objects')
    class Fig:
        def __init__(self,*a,**k): pass
        def to_html(self, **k):
            return '<html></html>'
    graph_objs.Figure = lambda *a, **k: Fig()
    class DummyScatter:
        def __init__(self, *a, **k):
            pass
    graph_objs.Scatter = DummyScatter
    dummy_plotly.graph_objects = graph_objs
    sys.modules['plotly'] = dummy_plotly
    sys.modules['plotly.graph_objects'] = graph_objs

    # fastapi minimal
    dummy_fastapi = types.ModuleType('fastapi')
    class DummyApp:
        def __init__(self,*a,**k): pass
        def on_event(self,*a,**k):
            def deco(fn):
                return fn
            return deco
        def middleware(self,*a,**k):
            return self.on_event()
        def get(self,*a,**k):
            return self.on_event()
        def post(self,*a,**k):
            return self.on_event()
        def delete(self,*a,**k):
            return self.on_event()
        def websocket(self,*a,**k):
            return self.on_event()
    dummy_fastapi.FastAPI = DummyApp
    dummy_fastapi.Depends = lambda x:x
    dummy_fastapi.HTTPException = DummyHTTPException
    dummy_fastapi.WebSocket = object
    dummy_fastapi.WebSocketDisconnect = Exception
    responses_mod = types.ModuleType('fastapi.responses')
    responses_mod.HTMLResponse = object
    responses_mod.StreamingResponse = object
    responses_mod.JSONResponse = object
    sys.modules['fastapi.responses'] = responses_mod
    security_mod = types.ModuleType('fastapi.security.api_key')
    security_mod.APIKeyHeader = lambda name: None
    sys.modules['fastapi.security.api_key'] = security_mod
    dummy_fastapi.responses = responses_mod
    dummy_fastapi.security = types.SimpleNamespace(api_key=security_mod)
    sys.modules['fastapi'] = dummy_fastapi

    sched_mod = types.ModuleType('apscheduler.schedulers.background')
    class DummyScheduler:
        def __init__(self, *a, **k): pass
        def add_job(self,*a,**k): pass
        def start(self): pass
        def get_job(self,*a,**k): return types.SimpleNamespace(next_run_time=None)
        def reschedule_job(self,*a,**k): pass
    sched_mod.BackgroundScheduler = DummyScheduler
    sys.modules['apscheduler.schedulers.background'] = sched_mod
    jobstore_mod = types.ModuleType('apscheduler.jobstores.sqlalchemy')
    jobstore_mod.SQLAlchemyJobStore = lambda url=None: None
    sys.modules['apscheduler.jobstores.sqlalchemy'] = jobstore_mod

    sys.modules.pop('crypto_screener_ai.web.dashboard', None)
    mod = importlib.import_module('crypto_screener_ai.web.dashboard')
    mod.DB_PATH = Path(tmp_path)
    mod.DB_FILE = mod.DB_PATH / 'db.sqlite'
    for name in ['requests', 'ccxt', 'plotly', 'plotly.graph_objects', 'fastapi',
                 'fastapi.responses', 'fastapi.security.api_key',
                 'apscheduler.schedulers.background', 'apscheduler.jobstores.sqlalchemy']:
        sys.modules.pop(name, None)
    return mod


def test_orderbook_caching(tmp_path):
    mod = load_dashboard(tmp_path)
    import asyncio
    data = asyncio.run(mod.get_orderbook('BTC/USDT'))
    cache = Path(mod.DB_PATH) / 'orderbook_BTCUSDT.json'
    assert cache.exists()
    assert data['bids']


def test_compute_rebalance(tmp_path):
    mod = load_dashboard(tmp_path)
    conn = mod.get_db()
    conn.execute('INSERT INTO portfolio(symbol, quantity) VALUES(?,?)', ('BTC', 1))
    conn.execute('INSERT INTO portfolio(symbol, quantity) VALUES(?,?)', ('ETH', 1))
    conn.commit()
    conn.close()
    trades = mod.compute_rebalance()
    assert len(trades) == 2


def test_strategy_history(tmp_path):
    mod = load_dashboard(tmp_path)
    conn = mod.get_db()
    conn.execute('INSERT INTO strategy_history(name, ts, return_pct) VALUES (?,?,?)', ('BTC', 't', 5))
    conn.commit()
    conn.close()
    import asyncio
    resp = asyncio.run(mod.analytics_strategy('BTC'))
    assert 'average_return_pct' in resp


def test_webhook_register(tmp_path):
    mod = load_dashboard(tmp_path)
    import asyncio
    asyncio.run(mod.add_webhook({'url': 'http://example.com'}, user={'role':'admin'}))
    urls = mod.load_webhook_urls()
    assert 'http://example.com' in urls


