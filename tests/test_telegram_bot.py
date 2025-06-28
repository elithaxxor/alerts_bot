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
        messages.append((data['chat_id'], data['text']))
        return types.SimpleNamespace()
    dummy_requests.post = post
    monkeypatch.setitem(sys.modules, 'requests', dummy_requests)

    dummy_backtest = types.ModuleType('crypto_screener_ai.app.backtest')
    dummy_backtest.run_backtest = lambda symbol: {'return_pct': 5.0}
    monkeypatch.setitem(sys.modules, 'crypto_screener_ai.app.backtest', dummy_backtest)

    sys.modules.pop('telegram_bot', None)
    bot = importlib.import_module('telegram_bot')
    bot.BASE_URL = 'http://test'
    bot.PORTFOLIO_PATH = Path(tmp_path) / 'portfolio.json'
    return bot, messages


def test_buy_and_sell(tmp_path, monkeypatch):
    bot, msgs = load_bot(tmp_path, monkeypatch)
    bot.process_update({'message': {'chat': {'id': 1}, 'text': '/buy BTC 2'}})
    data = json.loads(Path(bot.PORTFOLIO_PATH).read_text())
    assert data['BTC'] == 2
    bot.process_update({'message': {'chat': {'id': 1}, 'text': '/sell BTC 1'}})
    data = json.loads(Path(bot.PORTFOLIO_PATH).read_text())
    assert data['BTC'] == 1
    assert msgs[-1][1] == 'Order executed'


def test_unauthorized_trade(tmp_path, monkeypatch):
    bot, msgs = load_bot(tmp_path, monkeypatch, allowed='2')
    bot.process_update({'message': {'chat': {'id': 1}, 'text': '/buy BTC 1'}})
    assert not Path(bot.PORTFOLIO_PATH).exists()
    assert msgs[-1][1] == 'Not authorized'


def test_backtest(tmp_path, monkeypatch):
    bot, msgs = load_bot(tmp_path, monkeypatch)
    bot.process_update({'message': {'chat': {'id': 1}, 'text': '/backtest BTC'}})
    assert msgs[-1][1].startswith('Return:')

