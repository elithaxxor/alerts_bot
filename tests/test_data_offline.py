import sys, json
from pathlib import Path
import types, importlib
import pytest

pytest.importorskip("pandas")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_data_fetcher_offline(monkeypatch):
    class DummyExchange:
        def fetch_ticker(self, *a, **k):
            raise AssertionError('network should not be called')

        def fetch_ohlcv(self, *a, **k):
            raise AssertionError('network should not be called')

    dummy_ccxt = types.ModuleType('ccxt')
    dummy_ccxt.binance = lambda *a, **k: DummyExchange()
    monkeypatch.setitem(sys.modules, 'ccxt', dummy_ccxt)

    price_cache = Path('data/price_btcusdt.json')
    ohlcv_cache = Path('data/ohlcv_btcusdt_1h.json')
    price_cache.write_text(json.dumps(123.45))
    ohlcv_cache.write_text(json.dumps([[0, 1, 2, 3, 4, 5]]))

    monkeypatch.setenv('OFFLINE_MODE', '1')

    data_mod = importlib.import_module('trading_bot.data')
    fetcher = data_mod.DataFetcher('BTC/USDT')

    price = fetcher.get_current_price()
    df = fetcher.get_ohlcv('1h', limit=1)

    assert price == 123.45
    assert len(df) == 1

    price_cache.unlink()
    ohlcv_cache.unlink()
