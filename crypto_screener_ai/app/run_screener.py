#!/usr/bin/env python
"""
run_screener.py – call OpenAI with your CryptoScreener prompt template

New features:
  • --symbol or -s lets you analyse any extra coin on-the-fly
  • Automatically appends top-25-by-volume (CoinGecko) to the watch-list
  • Adds Task 8 asking for five best ideas in next 30 min
"""
import argparse
import datetime
import json
import os
import uuid
import requests
from pathlib import Path
from dotenv import load_dotenv
from rich import print
from openai import OpenAI

# ---------- helpers -----------------------------------------------------------
def fetch_top_25_volume(vs_currency: str = "usd") -> list[str]:
    cache_file = Path(__file__).resolve().parents[2] / "data" / "top25_cache.json"
    if os.getenv("OFFLINE_MODE"):
        return json.loads(cache_file.read_text())

    url = (
        "https://api.coingecko.com/api/v3/coins/markets"
        f"?vs_currency={vs_currency}&order=volume_desc&per_page=25&page=1"
    )
    try:
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        return [coin["symbol"].upper() for coin in res.json()]
    except Exception as exc:
        print(
            f"[yellow]⚠️  Could not fetch top-25 volume list ({exc}); "
            "continuing with defaults.[/]"
        )
        return json.loads(cache_file.read_text())

# ---------- main --------------------------------------------------------------
def main():
    load_dotenv()
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    parser = argparse.ArgumentParser(
        description="Run CryptoScreenerAI prompt through OpenAI Completion")
    parser.add_argument("-s", "--symbol", help="Extra symbol to analyse (e.g. DOGE)")
    args = parser.parse_args()

    # base watch-list
    symbols = ["SOL","ETH","BTC","BNB","XRP","QNT","TON","ETC",
               "AVAX","ADA","ALGO","LTC"]

    # add top-25 volume
    symbols += [sym for sym in fetch_top_25_volume() if sym not in symbols]

    # add optional user-requested symbol
    if args.symbol:
        symbols.append(args.symbol.upper())

    # compose parameter bundle
    params = {
        "run_id": str(uuid.uuid4()),
        "as_of": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "symbols": symbols,
        "leverage": 50,
        "budget_per_order_min": 5,
        "budget_per_order_max": 20,
        "budget_per_coin_max": 50,
        "watch_windows": ["30m","1h","2h-4h","4h-8h"],
        "data_sources": {
            "price": "CoinGecko",
            "order_book": "Binance",
            "sentiment": ["Twitter","Reddit","Telegram","GoogleTrends"],
            "macro": ["DXY","SPX","US10Y"]
        }
    }

    template_path = Path(__file__).with_name("prompt_template.txt")
    template = template_path.read_text()

    user_prompt = template.replace("<<TASK PARAMETERS>>",
                                   json.dumps(params, indent=2))

    messages = [
        {"role": "system", "content":
            template.split("USER MESSAGE TEMPLATE")[0]},
        {"role": "user", "content": user_prompt},
        {"role": "assistant", "content": "Return JSON only."}
    ]

    print("[bold cyan]🚀  Requesting analysis …[/]")
    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=messages,
        temperature=0.3,
        max_tokens=2800
    )

    reply = response.choices[0].message.content
    Path("last_response.json").write_text(reply)
    print("\n[green]LLM response saved to last_response.json[/]")

if __name__ == "__main__":
    main()
