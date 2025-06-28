import time
from collections import defaultdict
from typing import Callable, Any

# service -> {count, failures, duration}
API_METRICS: dict[str, dict[str, float]] = defaultdict(lambda: {
    "count": 0,
    "failures": 0,
    "duration": 0.0,
})


def record_api_call(service: str, func: Callable[..., Any], *args, **kwargs) -> Any:
    """Execute func while recording metrics for the given service."""
    start = time.perf_counter()
    try:
        return func(*args, **kwargs)
    except Exception:
        API_METRICS[service]["failures"] += 1
        raise
    finally:
        API_METRICS[service]["count"] += 1
        API_METRICS[service]["duration"] += time.perf_counter() - start
