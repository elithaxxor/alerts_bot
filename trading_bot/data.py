import ccxt
import pandas as pd
import json
import os
from pathlib import Path

class DataFetcher:
    """Fetch market data from Binance via ccxt."""
    def __init__(self, symbol: str = "BTC/USDT"):  
        self.symbol = symbol
        self.exchange = ccxt.binance({"enableRateLimit": True})

    def get_current_price(self) -> float:
        """Return last trade price with optional offline fallback."""
        cache_path = (
            Path(__file__).resolve().parents[1]
            / "data"
            / f"price_{self.symbol.replace('/', '').lower()}.json"
        )

        if os.getenv("OFFLINE_MODE") and cache_path.exists():
            return json.loads(cache_path.read_text())

        try:
            ticker = self.exchange.fetch_ticker(self.symbol)
            price = ticker["last"]
            cache_path.write_text(json.dumps(price))
            return price
        except Exception:
            if cache_path.exists():
                return json.loads(cache_path.read_text())
            raise

    def get_ohlcv(self, timeframe: str = "1h", limit: int = 500) -> pd.DataFrame:
        """Return OHLCV data with optional offline fallback."""
        cache_path = (
            Path(__file__).resolve().parents[1]
            / "data"
            / f"ohlcv_{self.symbol.replace('/', '').lower()}_{timeframe}.json"
        )

        if os.getenv("OFFLINE_MODE") and cache_path.exists():
            cached = json.loads(cache_path.read_text())
            df = pd.DataFrame(
                cached, columns=["timestamp", "open", "high", "low", "close", "volume"]
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            return df

        try:
            data = self.exchange.fetch_ohlcv(
                self.symbol, timeframe=timeframe, limit=limit
            )
            df = pd.DataFrame(
                data, columns=["timestamp", "open", "high", "low", "close", "volume"]
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            cache_path.write_text(json.dumps(data))
            return df
        except Exception:
            if cache_path.exists():
                cached = json.loads(cache_path.read_text())
                df = pd.DataFrame(
                    cached,
                    columns=["timestamp", "open", "high", "low", "close", "volume"],
                )
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
                return df
            raise
