import sys
import json
from pathlib import Path
import types
import pytest

pd = pytest.importorskip("pandas")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trading_bot.data import DataFetcher


def test_data_fetcher_offline(monkeypatch):
    price_cache = Path('data/price_btcusdt.json')
    ohlcv_cache = Path('data/ohlcv_btcusdt_1h.csv')

    df = pd.DataFrame({
        'timestamp': pd.date_range('2024-01-01', periods=3, freq='H'),
        'open': [1, 2, 3],
        'high': [2, 3, 4],
        'low': [0.5, 1.5, 2.5],
        'close': [1.5, 2.5, 3.5],
        'volume': [10, 20, 30]
    })

    price_cache.write_text(json.dumps(123.45))
    df.to_csv(ohlcv_cache, index=False)

    monkeypatch.setenv('OFFLINE_MODE', '1')

    fetcher = DataFetcher('BTC/USDT')
    fetcher.exchange = types.SimpleNamespace(
        fetch_ticker=lambda *a, **k: (_ for _ in ()).throw(AssertionError('net')),
        fetch_ohlcv=lambda *a, **k: (_ for _ in ()).throw(AssertionError('net'))
    )

    price = fetcher.get_current_price()
    data = fetcher.get_ohlcv(limit=3)

    assert price == 123.45
    assert len(data) == 3

    price_cache.unlink()
    ohlcv_cache.unlink()
