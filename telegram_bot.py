import os
import time
import json
from pathlib import Path
import requests
from typing import Dict

from crypto_screener_ai.app.backtest import run_backtest

API_TOKEN = os.getenv('TELEGRAM_TOKEN')
BASE_URL = f"https://api.telegram.org/bot{API_TOKEN}" if API_TOKEN else None
ALLOWED_IDS = [int(x) for x in os.getenv("TELEGRAM_ALLOWED_IDS", "").split(",") if x.strip()]
PORTFOLIO_PATH = Path("data/telegram_portfolio.json")


def send_message(chat_id: int, text: str):
    if not BASE_URL:
        return
    try:
        requests.post(f"{BASE_URL}/sendMessage", data={'chat_id': chat_id, 'text': text}, timeout=10)
    except Exception:
        pass


def fetch_strategy_summary(name: str) -> str:
    url = f"http://localhost:9999/strategies/{name}"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code != 200:
            return "Strategy not found"
        js = res.json()
        return (js.get('code', '') or '')[:400]
    except Exception:
        return 'Error fetching strategy'


def load_portfolio() -> Dict[str, float]:
    if PORTFOLIO_PATH.exists():
        try:
            return json.loads(PORTFOLIO_PATH.read_text())
        except Exception:
            return {}
    return {}


def save_portfolio(data: Dict[str, float]):
    PORTFOLIO_PATH.write_text(json.dumps(data))


def update_portfolio(symbol: str, qty: float):
    port = load_portfolio()
    sym = symbol.upper()
    port[sym] = port.get(sym, 0) + qty
    if abs(port[sym]) < 1e-8:
        port.pop(sym)
    save_portfolio(port)


def run_bot(poll_interval: int = 5):
    if not BASE_URL:
        raise RuntimeError('TELEGRAM_TOKEN not set')
    offset = 0
    while True:
        try:
            resp = requests.get(f"{BASE_URL}/getUpdates", params={'timeout': 30, 'offset': offset+1}, timeout=35)
            resp.raise_for_status()
            data = resp.json().get('result', [])
            for update in data:
                offset = update['update_id']
                process_update(update)
        except Exception:
            time.sleep(poll_interval)
            continue
        time.sleep(poll_interval)


def process_update(update: Dict):
    msg = update.get('message', {})
    chat_id = msg.get('chat', {}).get('id')
    text = msg.get('text', '')
    if not chat_id or not text:
        return

    if text.startswith('/strategy '):
        name = text.split(' ', 1)[1]
        summary = fetch_strategy_summary(name)
        send_message(chat_id, summary)
        return

    if text.startswith('/backtest '):
        symbol = text.split(' ', 1)[1].strip()
        try:
            result = run_backtest(symbol)
            reply = f"Return: {result.get('return_pct', 0)}%"
        except Exception as exc:
            reply = f"Error: {exc}"
        send_message(chat_id, reply)
        return

    if text.startswith('/buy ') or text.startswith('/sell '):
        if chat_id not in ALLOWED_IDS:
            send_message(chat_id, 'Not authorized')
            return
        parts = text.split()
        if len(parts) != 3:
            send_message(chat_id, 'Usage: /buy SYMBOL QTY')
            return
        symbol = parts[1]
        try:
            qty = float(parts[2])
        except ValueError:
            send_message(chat_id, 'Invalid quantity')
            return
        if text.startswith('/sell'):
            qty = -qty
        update_portfolio(symbol, qty)
        send_message(chat_id, 'Order executed')

