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
import ccxt
import plotly.graph_objects as go

from ..app import run_screener, backtest, security_audit

DB_PATH = Path(__file__).resolve().parents[1] / 'data'
DB_PATH.mkdir(exist_ok=True)
DB_FILE = DB_PATH / 'screener.db'

API_KEY = os.getenv('API_KEY', 'demo')
api_key_header = APIKeyHeader(name='X-API-Key')

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title='CryptoScreenerAI Dashboard')

SENTIMENT_DATA = {'sentiment': 'neutral', 'score': 0.0}
SOCIAL_POSTS: list[str] = []

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


def load_webhook_urls() -> list[str]:
    """Return list of custom webhook URLs from config file."""
    path = DB_PATH / 'webhooks.json'
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except Exception:
        return []


def save_webhook_urls(urls: list[str]):
    (DB_PATH / 'webhooks.json').write_text(json.dumps(urls))


def send_custom_webhooks(payload: str):
    """POST JSON payload to all registered webhook URLs."""
    for url in load_webhook_urls():
        try:
            requests.post(url, data=payload, headers={'Content-Type': 'application/json'}, timeout=10)
        except Exception as exc:
            logger.warning('Custom webhook %s failed: %s', url, exc)


def notify(message: str):
    send_push(message)
    send_email('CryptoScreenerAI Alert', message)
    send_slack(message)
    send_discord(message)
    send_custom_webhooks(json.dumps({'message': message}))


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
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
                        api_key TEXT PRIMARY KEY,
                        role TEXT
                    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS community_strategies (
                        name TEXT PRIMARY KEY,
                        code TEXT,
                        rating REAL DEFAULT 0,
                        votes INTEGER DEFAULT 0
                    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS strategy_history (
                        name TEXT,
                        ts TEXT,
                        return_pct REAL
                    )''')
    return conn


def require_key(key: str = Depends(api_key_header)) -> dict:
    """Validate API key and return user info."""
    conn = get_db()
    cur = conn.execute('SELECT role FROM users WHERE api_key = ?', (key,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {'api_key': key, 'role': row[0]}
    if key == API_KEY:
        return {'api_key': key, 'role': 'admin'}
    raise HTTPException(status_code=401, detail='Invalid API key')

def require_admin(user: dict = Depends(require_key)) -> dict:
    if user.get('role') != 'admin':
        raise HTTPException(status_code=403, detail='Admin role required')
    return user


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


@app.get('/sentiment/posts')
async def sentiment_posts():
    """Return cached list of trending social posts."""
    return {'posts': SOCIAL_POSTS}


@app.get('/predict/{symbol}')
async def predict(symbol: str):
    """Dummy short-term price prediction."""
    change = random.uniform(-0.05, 0.05)
    return {'symbol': symbol.upper(), 'predicted_change': change}


@app.get('/orderbook/{symbol}')
async def get_orderbook(symbol: str, limit: int = 20):
    """Return live order book and cache snapshot."""
    try:
        ex = ccxt.binance()
        data = ex.fetch_order_book(symbol, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    cache_file = DB_PATH / f'orderbook_{symbol.replace("/", "")}.json'
    cache_file.write_text(json.dumps(data))
    return data


@app.get('/portfolio')
async def get_portfolio(key: str = Depends(require_key)):
    conn = get_db()
    cur = conn.execute('SELECT symbol, quantity, entry_price FROM portfolio')
    rows = cur.fetchall()
    conn.close()
    return [{'symbol': r[0], 'quantity': r[1], 'entry_price': r[2]} for r in rows]


@app.post('/portfolio')
async def upsert_portfolio(item: dict, user: dict = Depends(require_admin)):
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
async def delete_portfolio(symbol: str, user: dict = Depends(require_admin)):
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


@app.get('/portfolio/risk/export')
async def portfolio_risk_export(format: str = 'json', key: str = Depends(require_key), days: int = 90):
    """Export portfolio risk metrics as JSON or CSV."""
    metrics = await portfolio_risk(key, days)
    if format == 'csv':
        def generate():
            yield 'sharpe_ratio,max_drawdown\n'
            if metrics:
                yield f"{metrics.get('sharpe_ratio',0)},{metrics.get('max_drawdown',0)}\n"
        return StreamingResponse(generate(), media_type='text/csv')
    return metrics


def compute_rebalance(strategy: str = 'equal') -> list[dict]:
    """Return trade suggestions to rebalance portfolio."""
    conn = get_db()
    rows = conn.execute('SELECT symbol, quantity FROM portfolio').fetchall()
    conn.close()
    holdings = [{'symbol': r[0], 'quantity': r[1]} for r in rows]
    if not holdings:
        return []
    symbols = ','.join({h['symbol'].lower() for h in holdings})
    url = f'https://api.coingecko.com/api/v3/simple/price?ids={symbols}&vs_currencies=usd'
    prices = requests.get(url, timeout=10).json()
    values = {h['symbol']: h['quantity'] * prices.get(h['symbol'].lower(), {}).get('usd', 0) for h in holdings}
    total = sum(values.values())
    if total == 0:
        return []
    if strategy != 'equal':
        raise HTTPException(status_code=400, detail='unsupported strategy')
    target = total / len(holdings)
    suggestions = []
    for h in holdings:
        current_val = values[h['symbol']]
        diff = target - current_val
        if abs(diff) < 1e-8:
            continue
        price = prices.get(h['symbol'].lower(), {}).get('usd', 0) or 1
        qty = diff / price
        suggestions.append({'symbol': h['symbol'], 'quantity_delta': round(qty, 8)})
    return suggestions


@app.get('/portfolio/rebalance')
async def portfolio_rebalance(strategy: str = 'equal', key: str = Depends(require_key)):
    return {'strategy': strategy, 'trades': compute_rebalance(strategy)}


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


@app.get('/community/strategies')
async def community_list():
    conn = get_db()
    rows = conn.execute('SELECT name, rating, votes FROM community_strategies').fetchall()
    conn.close()
    return [{'name': r[0], 'rating': r[1], 'votes': r[2]} for r in rows]


@app.get('/community/strategies/{name}')
async def community_get(name: str):
    conn = get_db()
    cur = conn.execute('SELECT name, code, rating, votes FROM community_strategies WHERE name = ?', (name,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail='Not found')
    return {'name': row[0], 'code': row[1], 'rating': row[2], 'votes': row[3]}


@app.post('/community/strategies')
async def community_add(item: dict, user: dict = Depends(require_key)):
    name = item.get('name')
    code = item.get('code')
    if not name or not code:
        raise HTTPException(status_code=400, detail='name and code required')
    conn = get_db()
    conn.execute('INSERT OR REPLACE INTO community_strategies(name, code) VALUES (?,?)', (name, code))
    conn.commit()
    conn.close()
    return {'status': 'ok'}


@app.post('/community/strategies/{name}/rate')
async def community_rate(name: str, data: dict, user: dict = Depends(require_key)):
    rating = float(data.get('rating', 0))
    if rating < 1 or rating > 5:
        raise HTTPException(status_code=400, detail='rating 1-5')
    conn = get_db()
    cur = conn.execute('SELECT rating, votes FROM community_strategies WHERE name=?', (name,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail='Not found')
    current_rating, votes = row
    new_votes = votes + 1
    new_rating = ((current_rating * votes) + rating) / new_votes
    conn.execute('UPDATE community_strategies SET rating=?, votes=? WHERE name=?', (new_rating, new_votes, name))
    conn.commit()
    conn.close()
    return {'status': 'ok', 'rating': round(new_rating, 2), 'votes': new_votes}


@app.get('/users')
async def list_users(user: dict = Depends(require_admin)):
    """List registered API keys and roles."""
    conn = get_db()
    rows = conn.execute('SELECT api_key, role FROM users').fetchall()
    conn.close()
    return [{'api_key': r[0], 'role': r[1]} for r in rows]


@app.post('/users/{api_key}')
async def upsert_user(api_key: str, data: dict, user: dict = Depends(require_admin)):
    """Create or update a user with the given API key."""
    role = data.get('role', 'user')
    conn = get_db()
    conn.execute('INSERT OR REPLACE INTO users(api_key, role) VALUES(?,?)', (api_key, role))
    conn.commit()
    conn.close()
    return {'status': 'ok'}


@app.delete('/users/{api_key}')
async def delete_user(api_key: str, user: dict = Depends(require_admin)):
    """Remove a user by API key."""
    conn = get_db()
    conn.execute('DELETE FROM users WHERE api_key = ?', (api_key,))
    conn.commit()
    conn.close()
    return {'status': 'ok'}


@app.get('/webhooks')
async def list_webhooks(user: dict = Depends(require_admin)):
    """Return registered webhook URLs."""
    return {'urls': load_webhook_urls()}


@app.post('/webhooks')
async def add_webhook(data: dict, user: dict = Depends(require_admin)):
    url = data.get('url')
    if not url:
        raise HTTPException(status_code=400, detail='url required')
    urls = load_webhook_urls()
    if url not in urls:
        urls.append(url)
    save_webhook_urls(urls)
    return {'status': 'ok', 'count': len(urls)}


@app.delete('/webhooks')
async def remove_webhook(data: dict, user: dict = Depends(require_admin)):
    url = data.get('url')
    urls = load_webhook_urls()
    if url in urls:
        urls.remove(url)
        save_webhook_urls(urls)
    return {'status': 'ok', 'count': len(urls)}


@app.get('/backtest/{symbol}')
async def run_backtest_api(symbol: str, days: int = 90, user: dict = Depends(require_admin)):
    try:
        result = backtest.run_backtest(symbol, days)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    conn = get_db()
    conn.execute('INSERT INTO strategy_history(name, ts, return_pct) VALUES(?,?,?)',
                 (symbol.upper(), result.get('generated_at'), result.get('return_pct')))
    conn.commit()
    conn.close()
    return result


@app.get('/backtest/{symbol}/export')
async def backtest_export(symbol: str, days: int = 90, format: str = 'json', user: dict = Depends(require_admin)):
    """Export backtest results as JSON or CSV."""
    try:
        result = backtest.run_backtest(symbol, days)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    if format == 'csv':
        def generate():
            yield 'symbol,period_days,trades,return_pct,generated_at\n'
            yield f"{result.get('symbol')},{result.get('period_days')},{result.get('trades')},{result.get('return_pct')},{result.get('generated_at')}\n"
        return StreamingResponse(generate(), media_type='text/csv')
    return result


def compute_analytics(limit: int = 5) -> dict:
    """Aggregate momentum scores from recent screener runs."""
    conn = get_db()
    cur = conn.execute('SELECT data FROM results ORDER BY ts DESC LIMIT ?', (limit,))
    rows = cur.fetchall()
    conn.close()
    scores: dict[str, list[float]] = {}
    for row in rows:
        js = json.loads(row[0])
        for sym, windows in js.get('screener', {}).items():
            for win in windows.values():
                scores.setdefault(sym, []).append(float(win.get('momentum_score', 0)))
    return {sym: (sum(vals) / len(vals)) if vals else 0.0 for sym, vals in scores.items()}


@app.get('/analytics/summary')
async def analytics_summary(limit: int = 5, key: str = Depends(require_key)):
    """Return average momentum score per symbol for recent runs."""
    return compute_analytics(limit)


@app.get('/analytics/report')
async def analytics_report(limit: int = 5, key: str = Depends(require_key)):
    """Return simple report highlighting top momentum symbols."""
    summary = compute_analytics(limit)
    top = sorted(summary.items(), key=lambda x: abs(x[1]), reverse=True)[:5]
    return {
        'top_symbols': [
            {'symbol': sym, 'avg_momentum': round(score, 3)} for sym, score in top
        ]
    }


@app.get('/analytics/strategy/{name}')
async def analytics_strategy(name: str, key: str = Depends(require_key)):
    """Aggregate historical backtest returns for a strategy."""
    conn = get_db()
    rows = conn.execute('SELECT ts, return_pct FROM strategy_history WHERE name=? ORDER BY ts', (name,)).fetchall()
    conn.close()
    if not rows:
        raise HTTPException(status_code=404, detail='Not found')
    dates = [r[0] for r in rows]
    returns = [r[1] for r in rows]
    avg_ret = sum(returns) / len(returns)
    fig = go.Figure([go.Scatter(x=dates, y=returns, mode='lines')])
    return {
        'average_return_pct': avg_ret,
        'chart_html': fig.to_html(include_plotlyjs=False)
    }


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


@app.get('/audit')
async def audit(user: dict = Depends(require_admin)):
    """Run basic security audit of strategies and dependencies."""
    report = {
        'strategies': security_audit.audit_strategies(),
        'dependencies': security_audit.audit_dependencies(),
    }
    return report


@app.get('/schedule/screener')
async def get_screener_schedule(user: dict = Depends(require_admin)):
    """Return next scheduled screener run."""
    job = scheduler.get_job('screener')
    ts = job.next_run_time.isoformat() if job and job.next_run_time else None
    return {'next_run': ts}


@app.post('/schedule/screener')
async def set_screener_schedule(data: dict, user: dict = Depends(require_admin)):
    """Adjust interval for the screener job in hours."""
    hours = float(data.get('hours', 1))
    scheduler.reschedule_job('screener', trigger='interval', hours=hours)
    return {'status': 'ok'}


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
        send_custom_webhooks(data)
        if event_loop:
            asyncio.run_coroutine_threadsafe(broadcast_update(data), event_loop)

def fetch_sentiment():
    """Update global sentiment data (placeholder implementation)."""
    SENTIMENT_DATA['sentiment'] = random.choice(['bullish', 'bearish', 'neutral'])
    SENTIMENT_DATA['score'] = round(random.uniform(-1, 1), 2)
    logger.info('Fetched sentiment: %s', SENTIMENT_DATA)


def fetch_social_posts():
    """Fetch trending Reddit posts as a simple sentiment feed."""
    global SOCIAL_POSTS
    url = 'https://www.reddit.com/r/CryptoCurrency/top.json?limit=5&t=day'
    try:
        res = requests.get(url, headers={'User-Agent': 'CryptoScreenerAI'}, timeout=10)
        res.raise_for_status()
        data = res.json()
        SOCIAL_POSTS = [child['data']['title'] for child in data['data']['children']]
        logger.info('Fetched %d social posts', len(SOCIAL_POSTS))
    except Exception as exc:
        logger.warning('Social posts update failed: %s', exc)


scheduler = BackgroundScheduler(
    jobstores={'default': SQLAlchemyJobStore(url=f'sqlite:///{DB_PATH / "jobs.db"}')}
)
scheduler.add_job(screener_job, 'interval', hours=1, id='screener')
scheduler.add_job(fetch_sentiment, 'interval', minutes=10, id='sentiment')
scheduler.add_job(fetch_social_posts, 'interval', minutes=15, id='social')
scheduler.start()

