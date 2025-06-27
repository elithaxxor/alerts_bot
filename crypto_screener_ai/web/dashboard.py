import json
import os
import sqlite3
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.security.api_key import APIKeyHeader
from apscheduler.schedulers.background import BackgroundScheduler

from ..app import run_screener

DB_PATH = Path(__file__).resolve().parents[1] / 'data'
DB_PATH.mkdir(exist_ok=True)
DB_FILE = DB_PATH / 'screener.db'

API_KEY = os.getenv('API_KEY', 'demo')
api_key_header = APIKeyHeader(name='X-API-Key')

app = FastAPI(title='CryptoScreenerAI Dashboard')


def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute('''CREATE TABLE IF NOT EXISTS results (
                        run_id TEXT PRIMARY KEY,
                        ts TEXT,
                        data TEXT
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


def screener_job():
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


scheduler = BackgroundScheduler()
scheduler.add_job(screener_job, 'interval', hours=1)
scheduler.start()

