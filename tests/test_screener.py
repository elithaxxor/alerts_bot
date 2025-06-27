import sys
import types
import importlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def load_module_with_mocks():
    # mock requests module
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
    dummy_requests._next_response = DummyResponse([])
    def get(url, timeout=10):
        return dummy_requests._next_response
    dummy_requests.get = get
    sys.modules['requests'] = dummy_requests

    # mock dotenv module
    dummy_dotenv = types.ModuleType('dotenv')
    def load_dotenv(*args, **kwargs):
        pass
    dummy_dotenv.load_dotenv = load_dotenv
    sys.modules['dotenv'] = dummy_dotenv

    # mock rich.print
    dummy_rich = types.ModuleType('rich')
    def dummy_print(*args, **kwargs):
        builtins.print(*args, **kwargs)
    import builtins
    dummy_rich.print = dummy_print
    sys.modules['rich'] = dummy_rich

    # mock openai module
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
        def __init__(self, *args, **kwargs):
            self.chat = types.SimpleNamespace(completions=DummyCompletions())
    dummy_openai.OpenAI = DummyClient
    sys.modules['openai'] = dummy_openai

    return importlib.import_module('crypto_screener_ai.app.run_screener')


def test_fetch_top_25_volume_success():
    mod = load_module_with_mocks()
    mod.requests._next_response = mod.requests.Response([{'symbol': 'eth'}, {'symbol': 'btc'}])
    cache_path = Path('data/top25_cache.json')
    original = cache_path.read_text()
    result = mod.fetch_top_25_volume()
    assert result == ['ETH', 'BTC']
    cache_path.write_text(original)


def test_fetch_top_25_volume_failure(capsys):
    mod = load_module_with_mocks()
    mod.requests._next_response = mod.requests.Response([], raise_exc=True)
    result = mod.fetch_top_25_volume()
    captured = capsys.readouterr()
    assert result == ["BTC", "ETH", "BNB", "XRP", "SOL"]
    assert 'Could not fetch top-25 volume list' in captured.out


def test_fetch_top_25_volume_offline(monkeypatch):
    mod = load_module_with_mocks()
    monkeypatch.setenv('OFFLINE_MODE', '1')
    result = mod.fetch_top_25_volume()
    assert result == ["BTC", "ETH", "BNB", "XRP", "SOL"]
