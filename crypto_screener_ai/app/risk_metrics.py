import math
from typing import List, Dict

from .backtest import fetch_historical_prices


def portfolio_history(holdings: List[Dict[str, float]], days: int = 90) -> List[float]:
    """Return portfolio value series for given holdings."""
    totals: List[float] | None = None
    for h in holdings:
        prices = fetch_historical_prices(h['symbol'], days)
        if len(prices) < days:
            continue
        series = [p * h['quantity'] for p in prices]
        if totals is None:
            totals = series
        else:
            totals = [x + y for x, y in zip(totals, series)]
    return totals or []


def sharpe_ratio(prices: List[float]) -> float:
    """Compute annualised Sharpe ratio of daily prices."""
    if len(prices) < 2:
        return 0.0
    returns = [(p2 - p1) / p1 for p1, p2 in zip(prices[:-1], prices[1:])]
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / len(returns)
    std = math.sqrt(variance)
    if std == 0:
        return 0.0
    return (mean / std) * math.sqrt(365)


def max_drawdown(prices: List[float]) -> float:
    """Return maximum drawdown percentage for a price series."""
    if not prices:
        return 0.0
    peak = prices[0]
    max_dd = 0.0
    for p in prices:
        if p > peak:
            peak = p
        drawdown = (peak - p) / peak
        if drawdown > max_dd:
            max_dd = drawdown
    return max_dd


def compute_portfolio_risk(holdings: List[Dict[str, float]], days: int = 90) -> Dict[str, float]:
    prices = portfolio_history(holdings, days)
    if not prices:
        return {"sharpe_ratio": 0.0, "max_drawdown": 0.0}
    return {
        "sharpe_ratio": round(sharpe_ratio(prices), 4),
        "max_drawdown": round(max_drawdown(prices), 4)
    }
