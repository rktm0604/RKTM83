"""
Simple process supervisor for RKTM83.

Run with:
  python supervisor.py

This script is designed to work well with NSSM on Windows. Point NSSM at this
file to keep the agent running continuously.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import time


logging.basicConfig(
    filename="supervisor.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("rktm83.supervisor")


def main() -> int:
    command = [sys.executable, "run_agent.py"]
    restart_count = 0

    while True:
        logger.info("Starting agent process: %s", command)
        process = subprocess.Popen(command)

        try:
            returncode = process.wait()
        except KeyboardInterrupt:
            logger.info("Supervisor interrupted. Stopping agent.")
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
            return 0

        if returncode == 0:
            logger.info("Agent exited cleanly with code 0. Supervisor stopping.")
            return 0

        restart_count += 1
        logger.warning(
            "Agent crashed with code %s. Restart #%s in 10 seconds.",
            returncode,
            restart_count,
        )
        time.sleep(10)


if __name__ == "__main__":
    raise SystemExit(main())
