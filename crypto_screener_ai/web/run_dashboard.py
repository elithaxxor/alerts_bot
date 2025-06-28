import subprocess
import sys
from pathlib import Path


def main():
    # run uvicorn on port 9999
    backend = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'crypto_screener_ai.web.dashboard:app', '--port', '9999'])
    # serve static frontend via simple http server on port 9998
    front_dir = Path(__file__).with_name('frontend')
    frontend = subprocess.Popen([sys.executable, '-m', 'http.server', '9998', '--directory', str(front_dir)])
    try:
        backend.wait()
    finally:
        frontend.terminate()
        backend.terminate()


if __name__ == '__main__':
    main()
