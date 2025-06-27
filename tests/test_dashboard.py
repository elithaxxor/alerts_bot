import sys
import types
import importlib
import json
from pathlib import Path
import pytest


class DummyHTTPException(Exception):
    def __init__(self, status_code: int = 500, detail: str | None = None):
        self.status_code = status_code
        self.detail = detail


def load_dashboard(tmp_path):
    # mock requests
    dummy_requests = types.ModuleType('requests')
    class DummyResponse:
        def __init__(self, data, raise_exc=False):
            self._data = data
            self.raise_exc = raise_exc
        def json(self):
            if self.raise_exc:
                raise ValueError('bad json')
            return self._data
        def raise_for_status(self):
            if self.raise_exc:
                raise Exception('err')
    dummy_requests.Response = DummyResponse
    dummy_requests._next_response = DummyResponse({'data':{'children':[{'data':{'title':'post1'}}]}})
    def get(*args, **kwargs):
        return dummy_requests._next_response
    dummy_requests.get = get
    sys.modules['requests'] = dummy_requests

    dummy_dotenv = types.ModuleType('dotenv')
    dummy_dotenv.load_dotenv = lambda *a, **k: None
    sys.modules['dotenv'] = dummy_dotenv

    dummy_rich = types.ModuleType('rich')
    dummy_rich.print = lambda *a, **k: None
    sys.modules['rich'] = dummy_rich

    dummy_openai = types.ModuleType('openai')
    class DummyCompletions:
        def create(self, **kwargs):
            class Msg:
                content = '{}'
            class Choice:
                message = Msg()
            class Resp:
                choices = [Choice()]
            return Resp()
    class DummyClient:
        def __init__(self, *a, **k):
            self.chat = types.SimpleNamespace(completions=DummyCompletions())
    dummy_openai.OpenAI = DummyClient
    sys.modules['openai'] = dummy_openai

    # mock fastapi
    dummy_fastapi = types.ModuleType('fastapi')
    class DummyApp:
        def __init__(self, *a, **k):
            pass
        def on_event(self, *a, **k):
            def deco(fn):
                return fn
            return deco
        def get(self, *a, **k):
            return self.on_event()
        def post(self, *a, **k):
            return self.on_event()
        def delete(self, *a, **k):
            return self.on_event()
        def websocket(self, *a, **k):
            return self.on_event()
    dummy_fastapi.FastAPI = DummyApp
    dummy_fastapi.Depends = lambda x: x
    dummy_fastapi.HTTPException = DummyHTTPException
    dummy_fastapi.WebSocket = object
    dummy_fastapi.WebSocketDisconnect = Exception
    responses_mod = types.ModuleType('fastapi.responses')
    responses_mod.HTMLResponse = object
    responses_mod.StreamingResponse = object
    sys.modules['fastapi.responses'] = responses_mod
    security_mod = types.ModuleType('fastapi.security.api_key')
    security_mod.APIKeyHeader = lambda name: None
    sys.modules['fastapi.security.api_key'] = security_mod
    dummy_fastapi.responses = responses_mod
    dummy_fastapi.security = types.SimpleNamespace(api_key=security_mod)
    sys.modules['fastapi'] = dummy_fastapi

    # mock apscheduler
    sched_mod = types.ModuleType('apscheduler.schedulers.background')
    class DummyScheduler:
        def __init__(self, *a, **k):
            pass
        def add_job(self, *a, **k):
            pass
        def start(self):
            pass
        def get_job(self, *a, **k):
            return types.SimpleNamespace(next_run_time=None)
        def reschedule_job(self, *a, **k):
            pass
    sched_mod.BackgroundScheduler = DummyScheduler
    sys.modules['apscheduler.schedulers.background'] = sched_mod

    jobstore_mod = types.ModuleType('apscheduler.jobstores.sqlalchemy')
    jobstore_mod.SQLAlchemyJobStore = lambda url=None: None
    sys.modules['apscheduler.jobstores.sqlalchemy'] = jobstore_mod

    # ensure fresh import
    sys.modules.pop('crypto_screener_ai.app.run_screener', None)
    mod = importlib.import_module('crypto_screener_ai.web.dashboard')
    mod.DB_FILE = Path(tmp_path) / 'test.db'
    # clean up to avoid side effects
    for name in ['requests', 'dotenv', 'rich', 'openai', 'fastapi', 'fastapi.responses',
                 'fastapi.security.api_key', 'apscheduler.schedulers.background',
                 'apscheduler.jobstores.sqlalchemy']:
        sys.modules.pop(name, None)
    return mod


def test_fetch_social_posts_success(tmp_path):
    mod = load_dashboard(tmp_path)
    mod.fetch_social_posts()
    assert mod.SOCIAL_POSTS == ['post1']


def test_require_admin_denied(tmp_path):
    mod = load_dashboard(tmp_path)
    conn = mod.get_db()
    conn.execute('INSERT INTO users(api_key, role) VALUES (?,?)', ('userkey', 'user'))
    conn.commit()
    conn.close()
    with pytest.raises(DummyHTTPException):
        mod.require_admin({'api_key': 'userkey', 'role': 'user'})


def test_compute_analytics(tmp_path):
    mod = load_dashboard(tmp_path)
    conn = mod.get_db()
    sample = {
        'screener': {
            'BTC': {
                '1h': {'momentum_score': 0.5},
                '4h': {'momentum_score': 0.3}
            },
            'ETH': {
                '1h': {'momentum_score': -0.2}
            }
        }
    }
    conn.execute('INSERT INTO results(run_id, ts, data) VALUES (?,?,?)',
                 ('id1', 't', json.dumps(sample)))
    conn.commit()
    conn.close()
    summary = mod.compute_analytics()
    assert round(summary['BTC'], 2) == 0.4
    assert round(summary['ETH'], 2) == -0.2
