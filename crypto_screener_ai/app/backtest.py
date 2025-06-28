import json
import os
import requests
from .monitoring import record_api_call
from typing import List, Dict, Callable
from pathlib import Path
import importlib.util
import datetime
import plotly.graph_objects as go


def fetch_historical_prices(symbol: str, days: int = 90) -> List[float]:
    """Fetch daily closing prices from CoinGecko or local cache."""
    cache_path = Path(__file__).resolve().parents[2] / 'data' / f'hist_{symbol.lower()}.json'

    if os.getenv('OFFLINE_MODE') and cache_path.exists():
        return json.loads(cache_path.read_text())

    url = (
        f"https://api.coingecko.com/api/v3/coins/{symbol.lower()}/market_chart"
        f"?vs_currency=usd&days={days}&interval=daily"
    )
    try:
        res = record_api_call("coingecko", requests.get, url, timeout=10)
        res.raise_for_status()
        data = res.json().get("prices", [])
        prices = [p[1] for p in data]
        cache_path.write_text(json.dumps(prices))
        return prices
    except Exception:
        if cache_path.exists():
            return json.loads(cache_path.read_text())
        raise


def simple_moving_average_cross(prices: List[float], short: int = 5, long: int = 20) -> Dict[str, float]:
    """Very basic moving average cross backtest."""
    if long >= len(prices):
        return {"trades": 0, "return_pct": 0.0}
    position = False
    entry_price = 0.0
    balance = 1.0
    for i in range(long, len(prices)):
        short_ma = sum(prices[i - short : i]) / short
        long_ma = sum(prices[i - long : i]) / long
        price = prices[i]
        if not position and short_ma > long_ma:
            position = True
            entry_price = price
        elif position and short_ma < long_ma:
            position = False
            balance *= price / entry_price
    if position:
        balance *= prices[-1] / entry_price
    return {
        "trades": 1 if balance != 1.0 else 0,
        "return_pct": round((balance - 1) * 100, 2),
    }


def load_strategy(name: str) -> Callable[[List[float]], Dict[str, float]]:
    """Dynamically load a strategy by name from the strategies folder."""
    strategy_dir = Path(__file__).resolve().parents[2] / "strategies"
    path = strategy_dir / f"{name}.py"
    if not path.exists():
        raise ValueError("Strategy not found")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    if hasattr(module, "Strategy"):
        strat_cls = getattr(module, "Strategy")
        strat = strat_cls()
        return strat.run
    if hasattr(module, "backtest"):
        return getattr(module, "backtest")
    raise ValueError("No Strategy or backtest callable in module")


def run_backtest(symbol: str, days: int = 90, strategy: str = "sma_cross") -> Dict[str, float]:
    prices = fetch_historical_prices(symbol, days)
    if not prices:
        raise ValueError("No data returned")
    try:
        strat_fn = load_strategy(strategy)
    except Exception:
        strat_fn = simple_moving_average_cross
    result = strat_fn(prices)
    result["symbol"] = symbol.upper()
    result["period_days"] = days
    result["generated_at"] = datetime.datetime.utcnow().isoformat() + "Z"
    # generate simple performance plot
    fig = go.Figure([go.Scatter(y=prices, mode="lines")])
    result["chart_html"] = fig.to_html(include_plotlyjs=False)
    return result
