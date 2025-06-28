import ccxt
import pandas as pd
from typing import List

class DataFetcher:
    """Fetch market data from Binance via ccxt."""
    def __init__(self, symbol: str = "BTC/USDT"):  
        self.symbol = symbol
        self.exchange = ccxt.binance({"enableRateLimit": True})

    def get_current_price(self) -> float:
        """Return last trade price."""
        ticker = self.exchange.fetch_ticker(self.symbol)
        return ticker['last']

    def get_ohlcv(self, timeframe: str = '1h', limit: int = 500) -> pd.DataFrame:
        """Return OHLCV data as a DataFrame."""
        data = self.exchange.fetch_ohlcv(self.symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(data, columns=['timestamp','open','high','low','close','volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
