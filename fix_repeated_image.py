"""One-off: replace a repeated stock photo in an already-posted Bitcoin
message with a real price chart, via Telegram's editMessageMedia - the
post stays in place, only its image changes. Tries the Fresh Live channel
bot first, then the old group's bot, since a message id alone doesn't say
which chat it's in."""

import json
import os

import requests

from price_chart import generate_price_chart

MESSAGE_ID = int(os.environ["MESSAGE_ID"])

CANDIDATES = [
    ("Fresh Live", os.environ.get("TELEGRAM_BOT_TOKEN_2"), os.environ.get("TELEGRAM_CHAT_ID_2")),
    ("Cryptocompass group", os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")),
]

chart = generate_price_chart("Bitcoin price chart")
if not chart:
    raise SystemExit("Could not generate a fresh Bitcoin chart - aborting, nothing was touched.")

found = False
for label, token, chat_id in CANDIDATES:
    if not token or not chat_id:
        print(f"{label}: skipped, missing token/chat_id secret.")
        continue

    resp = requests.post(
        f"https://api.telegram.org/bot{token}/editMessageMedia",
        data={
            "chat_id": chat_id,
            "message_id": MESSAGE_ID,
            "media": json.dumps({"type": "photo", "media": "attach://photo"}),
        },
        files={"photo": ("chart.png", chart, "image/png")},
        timeout=30,
    )
    result = resp.json()
    print(f"{label}: {result}")
    if result.get("ok"):
        print(f"Replaced the image in message {MESSAGE_ID} ({label}).")
        found = True
        break

if not found:
    print(f"Could not replace the image in message {MESSAGE_ID} in either chat.")
