"""Once-a-day guard for the scheduled posts.

Each daily post can be started two ways: an on-time external trigger, and
GitHub's own cron as a fallback (which has been running hours late). Whichever
fires first posts and marks the day; the other one sees the mark and exits.

    python daily_guard.py done NAME   # exit 0 if NAME already posted today (MSK)
    python daily_guard.py mark NAME   # record NAME as posted today
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

STATE_FILE = "data/daily_guard.json"
MSK = timezone(timedelta(hours=3))


def _load():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def main():
    action, name = sys.argv[1], sys.argv[2]
    today = datetime.now(MSK).strftime("%Y-%m-%d")
    state = _load()

    if action == "done":
        sys.exit(0 if state.get(name) == today else 1)

    state[name] = today
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
