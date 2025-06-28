import json
import os
from pathlib import Path

import ccxt
import pandas as pd
import json
import os
from pathlib import Path
from crypto_screener_ai.app.monitoring import record_api_call


class DataFetcher:
    """Fetch market data from Binance via ccxt with optional caching."""

    def __init__(self, symbol: str = "BTC/USDT"):
        self.symbol = symbol
        self.exchange = ccxt.binance({"enableRateLimit": True})
        self.cache_dir = Path(__file__).resolve().parents[1] / "data"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _price_cache(self) -> Path:
        sym = self.symbol.replace("/", "").lower()
        return self.cache_dir / f"price_{sym}.json"

    def _ohlcv_cache(self, timeframe: str) -> Path:
        sym = self.symbol.replace("/", "").lower()
        return self.cache_dir / f"ohlcv_{sym}_{timeframe}.csv"

    def get_current_price(self) -> float:
        """Return last trade price, using cache if OFFLINE_MODE is set."""
        cache_path = self._price_cache()

        if os.getenv("OFFLINE_MODE") and cache_path.exists():
            return json.loads(cache_path.read_text())

        try:
            ticker = record_api_call("binance", self.exchange.fetch_ticker, self.symbol)
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
            data = record_api_call(
                "binance",
                self.exchange.fetch_ohlcv,
                self.symbol,
                timeframe=timeframe,
                limit=limit,
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
        """Return OHLCV data as a DataFrame, using cache if OFFLINE_MODE is set."""
        cache_path = self._ohlcv_cache(timeframe)

        if os.getenv("OFFLINE_MODE") and cache_path.exists():
            df = pd.read_csv(cache_path)
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            return df.head(limit)

        try:
            data = self.exchange.fetch_ohlcv(self.symbol, timeframe=timeframe, limit=limit)
            df = pd.DataFrame(
                data,
                columns=["timestamp", "open", "high", "low", "close", "volume"],
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.to_csv(cache_path, index=False)
            return df
        except Exception:
            if cache_path.exists():
                df = pd.read_csv(cache_path)
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                return df.head(limit)
            raise
