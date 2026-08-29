"""One-off maintenance script: deletes all messages in the configured
Telegram chat by iterating sequential message ids. Run manually via the
"Purge channel history" workflow, never on a schedule.
"""
import os
import sys
import time

import requests

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

MAX_MESSAGE_ID = int(os.environ.get("PURGE_MAX_MESSAGE_ID", "300"))


def main():
    deleted = 0
    not_found = 0
    errors = []
    start = time.monotonic()

    for msg_id in range(1, MAX_MESSAGE_ID + 1):
        req_start = time.monotonic()
        try:
            resp = requests.post(
                f"{BASE}/deleteMessage",
                data={"chat_id": CHAT_ID, "message_id": msg_id},
                timeout=8,
            )
            data = resp.json()
        except Exception as e:
            errors.append((msg_id, f"request failed: {e}"))
            data = {}

        elapsed = time.monotonic() - req_start
        if data.get("ok"):
            deleted += 1
        else:
            desc = data.get("description", "")
            if "not found" in desc.lower() or "invalid" in desc.lower():
                not_found += 1
            elif desc:
                errors.append((msg_id, desc))

        if msg_id % 10 == 0 or elapsed > 2:
            print(
                f"[{time.monotonic() - start:.1f}s] id={msg_id} "
                f"deleted={deleted} not_found={not_found} errors={len(errors)} "
                f"(last call took {elapsed:.2f}s)",
                flush=True,
            )

        time.sleep(0.05)

    print(f"Deleted: {deleted}")
    print(f"Not found (no such message): {not_found}")
    print(f"Other errors: {len(errors)}")
    for mid, desc in errors[:30]:
        print(f"  id={mid}: {desc}")


if __name__ == "__main__":
    main()
