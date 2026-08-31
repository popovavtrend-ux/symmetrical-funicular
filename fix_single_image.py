"""One-off: replace one Cryptocompass group message's image (a flag-on-a-
building photo that didn't match the story) with a generic, non-flag
crypto/finance photo."""

import json
import os

import requests

from stock_image import find_stock_image

MESSAGE_ID = 266
TITLE_HINT = "cryptocurrency finance technology"

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
IMAGE_HISTORY_FILE = os.environ.get("IMAGE_HISTORY_FILE") or "data/seen_ids_images.json"

image_url = find_stock_image(TITLE_HINT, history_path=IMAGE_HISTORY_FILE)
if not image_url:
    raise SystemExit("Could not find a replacement image - aborting, nothing was touched.")

resp = requests.post(
    f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageMedia",
    data={
        "chat_id": CHAT_ID,
        "message_id": MESSAGE_ID,
        "media": json.dumps({"type": "photo", "media": image_url}),
    },
    timeout=30,
)
print(f"{MESSAGE_ID}: {resp.json()}")
