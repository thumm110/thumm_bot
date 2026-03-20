import time

from kalshi_bot.config import SLEEP_TIME
from kalshi_bot.pipeline import run_signal_pipeline

history = {}


def run():
    return run_signal_pipeline(history)


if __name__ == "__main__":
    while True:
        run()
        time.sleep(SLEEP_TIME)
