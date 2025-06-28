import pandas as pd
import pandas_ta as ta

class IndicatorCalculator:
    """Calculate common trading indicators."""

    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()

    def add_indicators(self) -> pd.DataFrame:
        df = self.df
        # VWAP using pandas_ta
        df['vwap'] = ta.vwap(df['high'], df['low'], df['close'], df['volume'])
        # Moving averages
        df['ma_20'] = ta.sma(df['close'], length=20)
        df['ma_50'] = ta.sma(df['close'], length=50)
        # RSI
        df['rsi'] = ta.rsi(df['close'])
        # ADX
        df['adx'] = ta.adx(df['high'], df['low'], df['close'])['ADX_14']
        # Bill Williams fractals
        df['fractal_up'] = ta.fractals(df['high'], df['low'])['FRAU_2']
        df['fractal_down'] = ta.fractals(df['high'], df['low'])['FRAD_2']
        return df

    def support_resistance(self, window: int = 20) -> pd.DataFrame:
        df = self.df
        df['support'] = df['low'].rolling(window=window).min()
        df['resistance'] = df['high'].rolling(window=window).max()
        return df[['support','resistance']]
