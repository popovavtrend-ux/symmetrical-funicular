"""One-off maintenance script: deletes all messages in the configured
Telegram chat by iterating sequential message ids. Run manually via the
"Purge channel history" workflow, never on a schedule.
"""
import os
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

    for msg_id in range(1, MAX_MESSAGE_ID + 1):
        resp = requests.post(
            f"{BASE}/deleteMessage",
            data={"chat_id": CHAT_ID, "message_id": msg_id},
            timeout=15,
        )
        data = resp.json()
        if data.get("ok"):
            deleted += 1
        else:
            desc = data.get("description", "")
            if "not found" in desc.lower() or "invalid" in desc.lower():
                not_found += 1
            else:
                errors.append((msg_id, desc))
        time.sleep(0.05)

    print(f"Deleted: {deleted}")
    print(f"Not found (no such message): {not_found}")
    print(f"Other errors: {len(errors)}")
    for mid, desc in errors[:30]:
        print(f"  id={mid}: {desc}")


if __name__ == "__main__":
    main()
