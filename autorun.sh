#!/usr/bin/env bash
set -e
pip install -r requirements.txt
echo "Launching CryptoScreenerAI dashboard on ports 9999 (API) and 9998 (frontend)"
python -m crypto_screener_ai.web.run_dashboard
