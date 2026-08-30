import os

import requests

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN_2"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID_2"]
MAX_MESSAGE_ID = int(os.environ.get("MAX_MESSAGE_ID") or "30")

deleted = 0
for message_id in range(1, MAX_MESSAGE_ID + 1):
    resp = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/deleteMessage",
        data={"chat_id": CHAT_ID, "message_id": message_id},
        timeout=30,
    )
    ok = resp.json().get("ok")
    if ok:
        deleted += 1
        print(f"Deleted message_id={message_id}")
    else:
        print(f"Skip message_id={message_id}: {resp.json().get('description')}")

print(f"Done. Deleted {deleted} message(s).")
