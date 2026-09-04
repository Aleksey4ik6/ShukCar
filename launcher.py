from __future__ import annotations

import argparse
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PYTHON = str(ROOT / ".venv" / "Scripts" / "python.exe")


def run_desktop():
    from main import run

    run()


def run_mobile():
    from mobile_main import run

    run()


def run_both():
    process = subprocess.Popen(
        [PYTHON, str(ROOT / "launcher.py"), "mobile"],
        cwd=str(ROOT),
    )
    try:
        time.sleep(2)
        run_desktop()
    finally:
        process.terminate()
        try:
            process.wait(timeout=8)
        except Exception:
            process.kill()


def main():
    parser = argparse.ArgumentParser(description="ShukCar unified launcher")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    subparsers.add_parser("desktop", help="Launch desktop application")
    subparsers.add_parser("mobile", help="Launch mobile-style desktop application")
    subparsers.add_parser("both", help="Launch desktop and mobile windows together")

    args = parser.parse_args()

    if args.mode == "desktop":
        run_desktop()
    elif args.mode == "mobile":
        run_mobile()
    elif args.mode == "both":
        run_both()
    else:
        parser.error("Unknown mode")


if __name__ == "__main__":
    main()
