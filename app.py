import streamlit as st
import pandas as pd
from trading_bot.data import DataFetcher
from trading_bot.indicators import IndicatorCalculator
from trading_bot.ml import PriceDirectionModel
from trading_bot.backtest import SimpleStrategy

st.set_page_config(page_title="Trading Bot Dashboard", layout="wide")

symbol = st.sidebar.text_input("Trading Pair", "BTC/USDT")
fetcher = DataFetcher(symbol)

@st.cache_data(ttl=60)
def load_data():
    df = fetcher.get_ohlcv(timeframe='1h', limit=240)
    calc = IndicatorCalculator(df)
    df = calc.add_indicators()
    df[['support','resistance']] = calc.support_resistance()
    return df

df = load_data()
current_price = fetcher.get_current_price()

st.sidebar.metric("Current Price", f"{current_price:.2f}")
st.sidebar.metric("Latest RSI", f"{df['rsi'].iloc[-1]:.2f}")

model = PriceDirectionModel()
model.fit(df)
prob = model.predict_proba(df)

st.sidebar.write(f"**AI Buy Probability:** {prob*100:.1f}%")

if st.button("Run Backtest"):
    strategy = SimpleStrategy(df)
    perf = strategy.run()
    st.sidebar.write(f"Backtest Return: {perf}%")

import plotly.graph_objects as go
fig = go.Figure()
fig.add_trace(go.Candlestick(x=df['timestamp'], open=df['open'], high=df['high'],
                             low=df['low'], close=df['close'], name='Price'))
fig.add_trace(go.Scatter(x=df['timestamp'], y=df['vwap'], name='VWAP'))
fig.add_trace(go.Scatter(x=df['timestamp'], y=df['ma_20'], name='MA20'))
fig.add_trace(go.Scatter(x=df['timestamp'], y=df['ma_50'], name='MA50'))
fig.update_layout(height=600)
st.plotly_chart(fig, use_container_width=True)
