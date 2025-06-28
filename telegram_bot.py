import os
import time
import json
from pathlib import Path
import requests
from typing import Dict

from trading_bot.data import DataFetcher

from crypto_screener_ai.app.backtest import run_backtest

API_TOKEN = os.getenv('TELEGRAM_TOKEN')
BASE_URL = f"https://api.telegram.org/bot{API_TOKEN}" if API_TOKEN else None
ALLOWED_IDS = [int(x) for x in os.getenv("TELEGRAM_ALLOWED_IDS", "").split(",") if x.strip()]
PORTFOLIO_PATH = Path("data/telegram_portfolio.json")
PORTFOLIO_CSV_PATH = Path("data/telegram_portfolio.csv")
ALERT_RULES_PATH = Path("data/alert_rules.json")

MESSAGES = {
    'en': {
        'not_auth': 'Not authorized',
        'usage': 'Usage: /buy SYMBOL QTY',
        'invalid_qty': 'Invalid quantity',
        'executed': 'Order executed',
        'pnl_header': 'PnL Summary',
        'alert_added': 'Alert added',
        'alert_triggered': 'Alert triggered'
    },
    'es': {
        'not_auth': 'No autorizado',
        'usage': 'Uso: /buy SIMBOLO CANTIDAD',
        'invalid_qty': 'Cantidad no válida',
        'executed': 'Orden ejecutada',
        'pnl_header': 'Resumen de PnL',
        'alert_added': 'Alerta agregada',
        'alert_triggered': 'Alerta activada'
    }
}

def tr(key: str, lang: str) -> str:
    lang = lang if lang in MESSAGES else 'en'
    return MESSAGES[lang].get(key, key)


def get_price(symbol: str) -> float:
    """Fetch current price from Binance via DataFetcher."""
    fetcher = DataFetcher(f"{symbol.upper()}/USDT")
    return float(fetcher.get_current_price())


def send_message(chat_id: int, text: str, reply_markup: dict | None = None):
    """Send a message via Telegram with optional inline keyboard."""
    if not BASE_URL:
        return
    payload = {'chat_id': chat_id, 'text': text}
    if reply_markup:
        payload['reply_markup'] = json.dumps(reply_markup)
    try:
        requests.post(f"{BASE_URL}/sendMessage", data=payload, timeout=10)
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


def load_portfolio() -> Dict[str, dict]:
    """Return portfolio mapping symbol -> {qty, avg_price}."""
    if PORTFOLIO_PATH.exists():
        try:
            data = json.loads(PORTFOLIO_PATH.read_text())
            for sym, val in list(data.items()):
                if isinstance(val, (int, float)):
                    data[sym] = {"qty": float(val), "avg_price": 0.0}
            return data
        except Exception:
            return {}
    return {}


def save_portfolio(data: Dict[str, dict]):
    PORTFOLIO_PATH.write_text(json.dumps(data))


def update_portfolio(symbol: str, qty: float, price: float):
    """Update holding quantity and average price."""
    port = load_portfolio()
    sym = symbol.upper()
    entry = port.get(sym, {"qty": 0.0, "avg_price": 0.0})
    if qty > 0:
        total_cost = entry["avg_price"] * entry["qty"] + price * qty
        entry["qty"] += qty
        entry["avg_price"] = total_cost / entry["qty"]
    else:
        entry["qty"] += qty
    if abs(entry["qty"]) < 1e-8:
        port.pop(sym, None)
    else:
        port[sym] = entry
    save_portfolio(port)


def export_portfolio_csv():
    """Save portfolio to CSV file."""
    port = load_portfolio()
    with PORTFOLIO_CSV_PATH.open("w") as fh:
        fh.write("symbol,qty,avg_price\n")
        for sym, info in port.items():
            fh.write(f"{sym},{info['qty']},{info.get('avg_price',0)}\n")


def import_portfolio_csv():
    """Load portfolio from CSV, replacing current file."""
    if not PORTFOLIO_CSV_PATH.exists():
        return False
    port: Dict[str, dict] = {}
    for line in PORTFOLIO_CSV_PATH.read_text().splitlines()[1:]:
        sym, qty, price = line.split(',')
        port[sym.upper()] = {"qty": float(qty), "avg_price": float(price)}
    save_portfolio(port)
    return True


def load_alert_rules() -> list:
    if ALERT_RULES_PATH.exists():
        try:
            return json.loads(ALERT_RULES_PATH.read_text())
        except Exception:
            return []
    return []


def save_alert_rules(rules: list):
    ALERT_RULES_PATH.write_text(json.dumps(rules))


def add_alert_rule(symbol: str, op: str, value: float, chat_id: int):
    rules = load_alert_rules()
    rules.append({"symbol": symbol.upper(), "op": op, "value": value, "chat_id": chat_id})
    save_alert_rules(rules)


def check_alert_rules():
    rules = load_alert_rules()
    if not rules:
        return
    for rule in list(rules):
        try:
            price = get_price(rule["symbol"])
        except Exception:
            continue
        if rule["op"] == ">" and price > rule["value"]:
            send_message(rule["chat_id"], f"{tr('alert_triggered','en')}: {rule['symbol']} {price} > {rule['value']}")
            rules.remove(rule)
        if rule["op"] == "<" and price < rule["value"]:
            send_message(rule["chat_id"], f"{tr('alert_triggered','en')}: {rule['symbol']} {price} < {rule['value']}")
            rules.remove(rule)
    save_alert_rules(rules)


def compute_pnl(lang: str) -> str:
    port = load_portfolio()
    if not port:
        return tr('pnl_header', lang) + ': empty'
    lines = [tr('pnl_header', lang) + ':']
    for sym, info in port.items():
        try:
            price = get_price(sym)
        except Exception:
            continue
        pnl = (price - info.get('avg_price', 0)) * info['qty']
        lines.append(f"{sym}: qty={info['qty']:.4f} pnl={pnl:.2f}")
    return '\n'.join(lines)


def send_trade_buttons(chat_id: int, symbol: str):
    kb = {
        "inline_keyboard": [
            [{"text": f"Buy {symbol}", "callback_data": f"BUY {symbol} 1"}],
            [{"text": f"Sell {symbol}", "callback_data": f"SELL {symbol} 1"}],
        ]
    }
    send_message(chat_id, f"Trade {symbol}", reply_markup=kb)


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
            check_alert_rules()
        except Exception:
            time.sleep(poll_interval)
            continue
        time.sleep(poll_interval)


def process_update(update: Dict):
    if 'callback_query' in update:
        data = update['callback_query']['data']
        chat_id = update['callback_query']['message']['chat']['id']
        update = {'message': {'chat': {'id': chat_id}, 'text': '/' + data.lower()}}
        process_update(update)
        return

    msg = update.get('message', {})
    chat_id = msg.get('chat', {}).get('id')
    text = msg.get('text', '')
    lang = msg.get('from', {}).get('language_code', 'en')[:2]
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
            send_message(chat_id, tr('not_auth', lang))
            return
        parts = text.split()
        if len(parts) != 3:
            send_message(chat_id, tr('usage', lang))
            return
        symbol = parts[1]
        try:
            qty = float(parts[2])
        except ValueError:
            send_message(chat_id, tr('invalid_qty', lang))
            return
        if text.startswith('/sell'):
            qty = -qty
        price = get_price(symbol)
        update_portfolio(symbol, qty, price)
        send_message(chat_id, tr('executed', lang))
        return

    if text.startswith('/pnl'):
        send_message(chat_id, compute_pnl(lang))
        return

    if text.startswith('/trade '):
        symbol = text.split()[1]
        send_trade_buttons(chat_id, symbol.upper())
        return

    if text.startswith('/export_portfolio'):
        export_portfolio_csv()
        send_message(chat_id, 'CSV exported')
        return

    if text.startswith('/import_portfolio'):
        if import_portfolio_csv():
            send_message(chat_id, 'CSV imported')
        else:
            send_message(chat_id, 'CSV not found')
        return

    if text.startswith('/alert '):
        try:
            _, sym, op, val = text.split()
            add_alert_rule(sym, op, float(val), chat_id)
            send_message(chat_id, tr('alert_added', lang))
        except Exception:
            send_message(chat_id, 'Usage: /alert SYMBOL >|< PRICE')
        return


