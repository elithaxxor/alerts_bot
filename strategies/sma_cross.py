"""Simple moving-average cross strategy."""

def backtest(prices, short=5, long=20):
    position = False
    entry = 0
    balance = 1.0
    for i in range(long, len(prices)):
        short_ma = sum(prices[i-short:i])/short
        long_ma = sum(prices[i-long:i])/long
        price = prices[i]
        if not position and short_ma > long_ma:
            position = True
            entry = price
        elif position and short_ma < long_ma:
            balance *= price/entry
            position = False
    if position:
        balance *= prices[-1]/entry
    return balance-1
