import importlib
import types
import sys
import json
from pathlib import Path

import pytest


def load_bot(tmp_path, monkeypatch, allowed='1'):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    monkeypatch.setenv('TELEGRAM_ALLOWED_IDS', allowed)
    monkeypatch.setenv('TELEGRAM_TOKEN', 'x')
    messages = []

    dummy_requests = types.ModuleType('requests')
    def post(url, data=None, timeout=10):
        messages.append((data['chat_id'], data['text'], data.get('reply_markup')))
        return types.SimpleNamespace()
    dummy_requests.post = post
    monkeypatch.setitem(sys.modules, 'requests', dummy_requests)

    dummy_backtest = types.ModuleType('crypto_screener_ai.app.backtest')
    dummy_backtest.run_backtest = lambda symbol: {'return_pct': 5.0}
    monkeypatch.setitem(sys.modules, 'crypto_screener_ai.app.backtest', dummy_backtest)

    dummy_data = types.ModuleType('trading_bot.data')
    class DummyFetcher:
        def __init__(self, symbol='BTC/USDT'):
            self.price = 100.0
        def get_current_price(self):
            return self.price
    dummy_data.DataFetcher = DummyFetcher
    monkeypatch.setitem(sys.modules, 'trading_bot.data', dummy_data)

    sys.modules.pop('telegram_bot', None)
    bot = importlib.import_module('telegram_bot')
    bot.BASE_URL = 'http://test'
    bot.PORTFOLIO_PATH = Path(tmp_path) / 'portfolio.json'
    bot.PORTFOLIO_CSV_PATH = Path(tmp_path) / 'portfolio.csv'
    bot.ALERT_RULES_PATH = Path(tmp_path) / 'alerts.json'
    return bot, messages


def test_buy_and_sell(tmp_path, monkeypatch):
    bot, msgs = load_bot(tmp_path, monkeypatch)
    bot.process_update({'message': {'chat': {'id': 1}, 'text': '/buy BTC 2'}})
    data = json.loads(Path(bot.PORTFOLIO_PATH).read_text())
    assert data['BTC']['qty'] == 2
    bot.process_update({'message': {'chat': {'id': 1}, 'text': '/sell BTC 1'}})
    data = json.loads(Path(bot.PORTFOLIO_PATH).read_text())
    assert data['BTC']['qty'] == 1
    assert msgs[-1][1] == 'Order executed'


def test_unauthorized_trade(tmp_path, monkeypatch):
    bot, msgs = load_bot(tmp_path, monkeypatch, allowed='2')
    bot.process_update({'message': {'chat': {'id': 1}, 'text': '/buy BTC 1'}})
    assert not Path(bot.PORTFOLIO_PATH).exists()
    assert msgs[-1][1] in ['Not authorized', 'No autorizado']


def test_backtest(tmp_path, monkeypatch):
    bot, msgs = load_bot(tmp_path, monkeypatch)
    bot.process_update({'message': {'chat': {'id': 1}, 'text': '/backtest BTC'}})
    assert msgs[-1][1].startswith('Return:')


def test_pnl_and_csv(tmp_path, monkeypatch):
    bot, msgs = load_bot(tmp_path, monkeypatch)
    prices = {'BTC': 100.0}
    monkeypatch.setattr(bot, 'get_price', lambda s: prices[s])
    bot.process_update({'message': {'chat': {'id': 1}, 'text': '/buy BTC 1', 'from': {'language_code': 'en'}}})
    prices['BTC'] = 110.0
    bot.process_update({'message': {'chat': {'id': 1}, 'text': '/pnl', 'from': {'language_code': 'en'}}})
    assert 'pnl=' in msgs[-1][1]
    bot.process_update({'message': {'chat': {'id': 1}, 'text': '/export_portfolio'}})
    assert Path(bot.PORTFOLIO_CSV_PATH).exists()
    Path(bot.PORTFOLIO_CSV_PATH).write_text('symbol,qty,avg_price\nETH,2,200')
    bot.process_update({'message': {'chat': {'id': 1}, 'text': '/import_portfolio'}})
    data = json.loads(Path(bot.PORTFOLIO_PATH).read_text())
    assert 'ETH' in data


def test_alert_rule_and_language(tmp_path, monkeypatch):
    bot, msgs = load_bot(tmp_path, monkeypatch)
    price = {'BTC': 90.0}
    monkeypatch.setattr(bot, 'get_price', lambda s: price[s])
    bot.process_update({'message': {'chat': {'id': 1}, 'text': '/alert BTC > 100', 'from': {'language_code': 'es'}}})
    price['BTC'] = 110.0
    bot.check_alert_rules()
    assert any('Alerta' in m[1] or 'Alert' in m[1] for m in msgs)

