import json
import os
import random
import sqlite3
import logging
import smtplib
import asyncio
from email.message import EmailMessage
import requests
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.security.api_key import APIKeyHeader
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
import csv

from ..app import run_screener, backtest

DB_PATH = Path(__file__).resolve().parents[1] / 'data'
DB_PATH.mkdir(exist_ok=True)
DB_FILE = DB_PATH / 'screener.db'

API_KEY = os.getenv('API_KEY', 'demo')
api_key_header = APIKeyHeader(name='X-API-Key')

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title='CryptoScreenerAI Dashboard')

SENTIMENT_DATA = {'sentiment': 'neutral', 'score': 0.0}

# websocket state
connections: set[WebSocket] = set()
event_loop = None


@app.on_event("startup")
async def capture_loop():
    global event_loop
    event_loop = asyncio.get_running_loop()


def send_push(message: str):
    """Send a push notification using the Pushover service if configured."""
    token = os.getenv('PUSHOVER_TOKEN')
    user = os.getenv('PUSHOVER_USER')
    if not token or not user:
        return
    try:
        requests.post('https://api.pushover.net/1/messages.json', data={
            'token': token,
            'user': user,
            'message': message,
        }, timeout=10)
    except Exception as exc:
        logger.warning('Push notification failed: %s', exc)


def send_email(subject: str, body: str):
    """Send an email alert using SMTP if credentials are provided."""
    host = os.getenv('SMTP_SERVER')
    user = os.getenv('SMTP_USER')
    password = os.getenv('SMTP_PASS')
    to_addr = os.getenv('ALERT_EMAIL')
    if not (host and user and password and to_addr):
        return
    try:
        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = user
        msg['To'] = to_addr
        msg.set_content(body)
        with smtplib.SMTP(host) as s:
            s.starttls()
            s.login(user, password)
            s.send_message(msg)
    except Exception as exc:
        logger.warning('Email alert failed: %s', exc)


def send_slack(message: str):
    """Send a Slack message via webhook if configured."""
    url = os.getenv('SLACK_WEBHOOK_URL')
    if not url:
        return
    try:
        requests.post(url, json={'text': message}, timeout=10)
    except Exception as exc:
        logger.warning('Slack alert failed: %s', exc)


def send_discord(message: str):
    """Send a Discord message via webhook if configured."""
    url = os.getenv('DISCORD_WEBHOOK_URL')
    if not url:
        return
    try:
        requests.post(url, json={'content': message}, timeout=10)
    except Exception as exc:
        logger.warning('Discord alert failed: %s', exc)


def notify(message: str):
    send_push(message)
    send_email('CryptoScreenerAI Alert', message)
    send_slack(message)
    send_discord(message)


def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute('''CREATE TABLE IF NOT EXISTS results (
                        run_id TEXT PRIMARY KEY,
                        ts TEXT,
                        data TEXT
                    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS portfolio (
                        symbol TEXT PRIMARY KEY,
                        quantity REAL,
                        entry_price REAL
                    )''')
    return conn


def require_key(key: str = Depends(api_key_header)):
    if key != API_KEY:
        raise HTTPException(status_code=401, detail='Invalid API key')


@app.get('/', response_class=HTMLResponse)
async def index():
    html = (Path(__file__).with_name('frontend') / 'index.html').read_text()
    return HTMLResponse(html)


@app.get('/results/latest')
async def latest(key: str = Depends(require_key)):
    conn = get_db()
    cur = conn.execute('SELECT data FROM results ORDER BY ts DESC LIMIT 1')
    row = cur.fetchone()
    conn.close()
    if not row:
        return {}
    return json.loads(row[0])


@app.get('/results/{run_id}')
async def get_result(run_id: str, key: str = Depends(require_key)):
    conn = get_db()
    cur = conn.execute('SELECT data FROM results WHERE run_id = ?', (run_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail='Not found')
    return json.loads(row[0])


@app.get('/results/export')
async def export_results(format: str = 'json', key: str = Depends(require_key)):
    """Export all stored results as JSON or CSV."""
    conn = get_db()
    cur = conn.execute('SELECT run_id, ts, data FROM results ORDER BY ts')
    rows = cur.fetchall()
    conn.close()
    if format == 'csv':
        def generate():
            yield 'run_id,ts,data\n'
            for r in rows:
                yield f"{r[0]},{r[1]}," + json.dumps(json.loads(r[2])) + "\n"
        return StreamingResponse(generate(), media_type='text/csv')
    return [json.loads(r[2]) for r in rows]


@app.websocket('/ws/results')
async def ws_results(websocket: WebSocket):
    await websocket.accept()
    connections.add(websocket)
    conn = get_db()
    cur = conn.execute('SELECT data FROM results ORDER BY ts DESC LIMIT 1')
    row = cur.fetchone()
    conn.close()
    if row:
        await websocket.send_text(row[0])
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        connections.discard(websocket)


async def broadcast_update(data: str):
    """Send JSON string to all connected WebSocket clients."""
    for ws in list(connections):
        try:
            await ws.send_text(data)
        except Exception:
            connections.discard(ws)


@app.get('/sentiment')
async def sentiment():
    """Return the most recently fetched sentiment data."""
    return SENTIMENT_DATA


@app.get('/predict/{symbol}')
async def predict(symbol: str):
    """Dummy short-term price prediction."""
    change = random.uniform(-0.05, 0.05)
    return {'symbol': symbol.upper(), 'predicted_change': change}


@app.get('/portfolio')
async def get_portfolio(key: str = Depends(require_key)):
    conn = get_db()
    cur = conn.execute('SELECT symbol, quantity, entry_price FROM portfolio')
    rows = cur.fetchall()
    conn.close()
    return [{'symbol': r[0], 'quantity': r[1], 'entry_price': r[2]} for r in rows]


@app.post('/portfolio')
async def upsert_portfolio(item: dict, key: str = Depends(require_key)):
    symbol = item.get('symbol', '').upper()
    qty = float(item.get('quantity', 0))
    entry = float(item.get('entry_price', 0))
    if not symbol:
        raise HTTPException(status_code=400, detail='symbol required')
    conn = get_db()
    conn.execute('INSERT OR REPLACE INTO portfolio(symbol, quantity, entry_price)'
                 ' VALUES(?,?,?)', (symbol, qty, entry))
    conn.commit()
    conn.close()
    return {'status': 'ok'}


@app.delete('/portfolio/{symbol}')
async def delete_portfolio(symbol: str, key: str = Depends(require_key)):
    conn = get_db()
    conn.execute('DELETE FROM portfolio WHERE symbol = ?', (symbol.upper(),))
    conn.commit()
    conn.close()
    return {'status': 'ok'}


@app.get('/portfolio/pnl')
async def portfolio_pnl(key: str = Depends(require_key)):
    conn = get_db()
    cur = conn.execute('SELECT symbol, quantity, entry_price FROM portfolio')
    rows = cur.fetchall()
    conn.close()
    holdings = [{'symbol': r[0], 'quantity': r[1], 'entry_price': r[2]} for r in rows]
    symbols = ','.join({h['symbol'].lower() for h in holdings})
    if not symbols:
        return []
    url = f'https://api.coingecko.com/api/v3/simple/price?ids={symbols}&vs_currencies=usd'
    res = requests.get(url, timeout=10)
    res.raise_for_status()
    prices = res.json()
    results = []
    for h in holdings:
        current = prices.get(h['symbol'].lower(), {}).get('usd', 0)
        pnl = (current - h['entry_price']) * h['quantity']
        results.append({**h, 'current_price': current, 'pnl': pnl})
    return results


@app.get('/portfolio/risk')
async def portfolio_risk(key: str = Depends(require_key), days: int = 90):
    """Return portfolio-level Sharpe ratio and max drawdown."""
    conn = get_db()
    cur = conn.execute('SELECT symbol, quantity FROM portfolio')
    rows = cur.fetchall()
    conn.close()
    holdings = [{'symbol': r[0], 'quantity': r[1]} for r in rows]
    if not holdings:
        return {}
    try:
        from ..app import risk_metrics
        metrics = risk_metrics.compute_portfolio_risk(holdings, days)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return metrics


@app.get('/strategies')
async def list_strategies():
    """List available strategy files."""
    files = []
    strategy_dir = Path(__file__).resolve().parents[1] / 'strategies'
    if strategy_dir.exists():
        files = [f.name for f in strategy_dir.glob('*.py')]
    return {'strategies': files}


@app.get('/strategies/{name}')
async def get_strategy(name: str):
    """Return the contents of a strategy file."""
    strategy_dir = Path(__file__).resolve().parents[1] / 'strategies'
    path = strategy_dir / name
    if not path.exists():
        raise HTTPException(status_code=404, detail='Not found')
    return {'name': name, 'code': path.read_text()}


@app.get('/backtest/{symbol}')
async def run_backtest_api(symbol: str, days: int = 90, key: str = Depends(require_key)):
    try:
        result = backtest.run_backtest(symbol, days)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return result


@app.post('/assistant')
async def assistant(query: dict, key: str = Depends(require_key)):
    """Very small natural-language helper for portfolio queries."""
    text = query.get('query', '').lower()
    if 'pnl' in text or 'p&l' in text:
        pnl = await portfolio_pnl(key)
        total = sum(item['pnl'] for item in pnl)
        return {'response': f'Total PnL is {total:.2f} USD'}
    if 'risk' in text:
        risk = await portfolio_risk(key)
        if not risk:
            return {'response': 'No holdings recorded.'}
        return {'response': f"Sharpe {risk.get('sharpe_ratio',0)}, Max DD {risk.get('max_drawdown',0)}"}
    if 'strategy' in text:
        strategies = (await list_strategies())['strategies']
        return {'response': 'Available strategies: ' + ', '.join(strategies)}
    return {'response': "I'm sorry, I can only answer questions about PnL, risk or strategies."}


@app.get('/health')
async def health():
    """Return timestamp and run ID of the most recent screener run."""
    conn = get_db()
    cur = conn.execute('SELECT run_id, ts FROM results ORDER BY ts DESC LIMIT 1')
    row = cur.fetchone()
    conn.close()
    if not row:
        return {'run_id': None, 'ts': None}
    return {'run_id': row[0], 'ts': row[1]}


def screener_job():
    logger.info('Running screener job')
    run_screener.main()
    path = Path('last_response.json')
    if path.exists():
        data = path.read_text()
        js = json.loads(data)
        conn = get_db()
        conn.execute('INSERT OR REPLACE INTO results(run_id, ts, data) VALUES(?, ?, ?)',
                     (js.get('run_id'), js.get('as_of'), data))
        conn.commit()
        conn.close()
        notify(f"New screener results stored: {js.get('run_id')}")
        if event_loop:
            asyncio.run_coroutine_threadsafe(broadcast_update(data), event_loop)

def fetch_sentiment():
    """Update global sentiment data (placeholder implementation)."""
    SENTIMENT_DATA['sentiment'] = random.choice(['bullish', 'bearish', 'neutral'])
    SENTIMENT_DATA['score'] = round(random.uniform(-1, 1), 2)
    logger.info('Fetched sentiment: %s', SENTIMENT_DATA)


scheduler = BackgroundScheduler(
    jobstores={'default': SQLAlchemyJobStore(url=f'sqlite:///{DB_PATH / "jobs.db"}')}
)
scheduler.add_job(screener_job, 'interval', hours=1)
scheduler.add_job(fetch_sentiment, 'interval', minutes=10)
scheduler.start()

