import pandas as pd

class SimpleStrategy:
    """Basic VWAP + RSI strategy for demonstration."""
    def __init__(self, df: pd.DataFrame):
        self.df = df

    def run(self):
        cash = 1.0
        position = 0.0
        for _, row in self.df.iterrows():
            if position == 0 and row['close'] > row['vwap'] and row['rsi'] < 30:
                position = cash / row['close']
                cash = 0.0
            elif position > 0 and (row['close'] < row['vwap'] or row['rsi'] > 70):
                cash = position * row['close']
                position = 0.0
        if position > 0:
            cash = position * self.df.iloc[-1]['close']
        return round((cash - 1.0)*100, 2)
