#!/bin/bash
set -e
pip install -r requirements.txt
python -m crypto_screener_ai.web.run_dashboard
