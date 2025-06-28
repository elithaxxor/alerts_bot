"""Simple moving-average cross strategy."""

from .base import Strategy


class SMACrossStrategy(Strategy):
    """Moving average cross implemented as a pluggable Strategy."""

    def __init__(self, short: int = 5, long: int = 20):
        self.short = short
        self.long = long

    def run(self, prices):
        """Execute the SMA cross strategy and return trade stats."""
        position = False
        entry = 0.0
        balance = 1.0
        trades = 0
        for i in range(self.long, len(prices)):
            short_ma = sum(prices[i - self.short : i]) / self.short
            long_ma = sum(prices[i - self.long : i]) / self.long
            price = prices[i]
            if not position and short_ma > long_ma:
                position = True
                entry = price
                trades += 1
            elif position and short_ma < long_ma:
                balance *= price / entry
                position = False
        if position:
            balance *= prices[-1] / entry
        return {
            "trades": trades,
            "return_pct": round((balance - 1) * 100, 2),
        }


def backtest(prices, short=5, long=20):
    """Backward compatible functional API returning trade stats."""
    strat = SMACrossStrategy(short=short, long=long)
    return strat.run(prices)

# Allow dynamic loaders to reference `Strategy` generically
Strategy = SMACrossStrategy
