# Feature Proposal

This repository currently provides a CLI script (`run_screener.py`) that submits a prompt to OpenAI and stores the response. The following improvements could significantly expand its usability and reliability.

## 1. Web-Based Dashboard
- **Framework**: Use FastAPI for API endpoints and a lightweight front end (e.g., Svelte or React) to display screening results.
- **Scheduling**: Run the screener at regular intervals via Celery or APScheduler and update a database (SQLite or PostgreSQL).
- **Authentication**: Simple API key or OAuth support for multiple users.
- **Visualization**: Integrate chart libraries (Plotly) for momentum, volatility and depth heat maps.

## 2. macOS Desktop App
- **Toolkit**: Leverage PyObjC or Electron to wrap the web interface as a standalone macOS application.
- **Notifications**: macOS Notification Center alerts when new trade setups appear.
- **Local Storage**: Cache recent API responses for offline viewing.

## 3. Reliability Improvements
- **Dependency Management**: Add a `requirements.txt` with pinned package versions.
- **Error Handling**: Gracefully report missing API keys or network failures.
- **Unit Tests**: Expand test coverage to include the CLI workflow and JSON schema validation.

## 4. Additional Analytics
- **On‑chain metrics**: Incorporate APIs such as Glassnode or Santiment for network statistics.
- **Social sentiment**: Schedule scrapers for Twitter/X, Reddit, and Telegram using official APIs where possible.
- **Backtesting module**: Allow users to evaluate historical strategy performance on selected pairs.

These features would transform the script into a comprehensive, user‑friendly platform for advanced crypto screening.

## 5. Complementary Features
- **Automated Deployment**: Provide a simple `autorun.sh` script that installs dependencies and launches the dashboard on ports 9999 and 9998.
- **Alerts**: Optional integration with Telegram or Discord webhooks to broadcast new screener results.
- **Caching & Backtesting**: Store past responses in SQLite to enable quick backtests and offline access.


## 6. Future Enhancements
- **TradingView Plugin**: Publish trading signals directly to TradingView or other charting platforms.
- **Mobile Support**: Ensure the dashboard scales cleanly to phones and tablets with responsive layouts.
- **Real‑time Sentiment Feed**: Incorporate streaming social and news sentiment to flag emerging events.
- **Predictive Models**: Experiment with ML techniques to forecast short‑term price movements.
- **Observability**: Add structured logging and metrics for easier troubleshooting and performance tuning.

