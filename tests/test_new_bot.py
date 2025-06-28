import pytest
pytest.importorskip('pandas')
pytest.importorskip('pandas_ta')

from trading_bot.data import DataFetcher
from trading_bot.indicators import IndicatorCalculator
from trading_bot.ml import PriceDirectionModel
from trading_bot.backtest import SimpleStrategy

class DummyExchange:
    def fetch_ticker(self, symbol):
        return {'last': 100.0}
    def fetch_ohlcv(self, symbol, timeframe='1h', limit=10):
        rows = []
        for i in range(limit):
            rows.append([i*3600000, 100+i, 101+i, 99+i, 100+i, 1])
        return rows

def test_data_fetcher(monkeypatch):
    monkeypatch.setattr('ccxt.binance', lambda *a, **k: DummyExchange())
    df = DataFetcher().get_ohlcv(limit=5)
    assert len(df) == 5
    assert 'close' in df.columns
    price = DataFetcher().get_current_price()
    assert price == 100.0

def test_indicators_and_ml(monkeypatch):
    monkeypatch.setattr('ccxt.binance', lambda *a, **k: DummyExchange())
    df = DataFetcher().get_ohlcv(limit=30)
    calc = IndicatorCalculator(df)
    df = calc.add_indicators()
    model = PriceDirectionModel()
    model.fit(df)
    prob = model.predict_proba(df)
    assert 0 <= prob <= 1

def test_backtest(monkeypatch):
    monkeypatch.setattr('ccxt.binance', lambda *a, **k: DummyExchange())
    df = DataFetcher().get_ohlcv(limit=30)
    calc = IndicatorCalculator(df)
    df = calc.add_indicators()
    strat = SimpleStrategy(df)
    result = strat.run()
    assert isinstance(result, float)
