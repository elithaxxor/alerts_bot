import os
import time
import requests

API_TOKEN = os.getenv('TELEGRAM_TOKEN')
BASE_URL = f"https://api.telegram.org/bot{API_TOKEN}" if API_TOKEN else None


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
                msg = update.get('message', {})
                chat_id = msg.get('chat', {}).get('id')
                text = msg.get('text', '')
                if not chat_id or not text:
                    continue
                if text.startswith('/strategy '):
                    name = text.split(' ', 1)[1]
                    summary = fetch_strategy_summary(name)
                    send_message(chat_id, summary)
        except Exception:
            time.sleep(poll_interval)
            continue
        time.sleep(poll_interval)
