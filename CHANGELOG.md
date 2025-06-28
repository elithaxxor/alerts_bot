# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]
- Added changelog and proposal links in documentation.
- Expanded feature proposal list.
- Implemented security audit CLI and `/audit` endpoint.
- Added offline mode using cached data when `OFFLINE_MODE` is set.
- Created community strategy hub with share and rating endpoints.
- Added CSV/JSON export endpoints for backtests and portfolio risk metrics.
- Added pluggable strategy loader and HTML report generation for backtests.
- Improved top volume fetcher with caching fallback for offline mode.
- Refactored DataFetcher caching to unify implementation and ensure data
  directory creation.

## [0.1.0] - 2024-03-01
- Initial release with CLI screener and dashboard.
