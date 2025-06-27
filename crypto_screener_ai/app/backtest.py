import datetime
import requests
from typing import List, Dict


def fetch_historical_prices(symbol: str, days: int = 90) -> List[float]:
    """Fetch daily closing prices from CoinGecko."""
    url = (
        f"https://api.coingecko.com/api/v3/coins/{symbol.lower()}/market_chart"
        f"?vs_currency=usd&days={days}&interval=daily"
    )
    res = requests.get(url, timeout=10)
    res.raise_for_status()
    data = res.json().get("prices", [])
    return [p[1] for p in data]


def simple_moving_average_cross(prices: List[float], short: int = 5, long: int = 20) -> Dict[str, float]:
    """Very basic moving average cross backtest."""
    if long >= len(prices):
        return {"trades": 0, "return_pct": 0.0}
    position = False
    entry_price = 0.0
    balance = 1.0
    for i in range(long, len(prices)):
        short_ma = sum(prices[i-short:i]) / short
        long_ma = sum(prices[i-long:i]) / long
        price = prices[i]
        if not position and short_ma > long_ma:
            position = True
            entry_price = price
        elif position and short_ma < long_ma:
            position = False
            balance *= price / entry_price
    if position:
        balance *= prices[-1] / entry_price
    return {"trades": 1 if balance != 1.0 else 0, "return_pct": round((balance-1)*100, 2)}


def run_backtest(symbol: str, days: int = 90) -> Dict[str, float]:
    prices = fetch_historical_prices(symbol, days)
    if not prices:
        raise ValueError("No data returned")
    result = simple_moving_average_cross(prices)
    result["symbol"] = symbol.upper()
    result["period_days"] = days
    result["generated_at"] = datetime.datetime.utcnow().isoformat() + "Z"
    return result
