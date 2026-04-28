"""Simple process watchdog for the trading engine."""

from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys
import time


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Restart live_trader.py if it exits")
    parser.add_argument("--interval", type=int, default=10)
    parser.add_argument("--max-restarts", type=int, default=20)
    parser.add_argument("--log", default="trader.log")
    parser.add_argument("--live", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    restarts = 0
    log_path = Path(args.log)
    command = [sys.executable, "live_trader.py"]
    if args.live:
        command.append("--live")

    while restarts < args.max_restarts:
        with log_path.open("a", encoding="utf-8") as log:
            log.write(f"\n[{datetime.now().isoformat(timespec='seconds')}] starting {command}\n")
            log.flush()
            proc = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=os.environ.copy())
            code = proc.wait()
            log.write(f"[{datetime.now().isoformat(timespec='seconds')}] exited code={code}\n")
        restarts += 1
        time.sleep(args.interval)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
