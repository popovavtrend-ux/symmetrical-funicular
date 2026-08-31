"""One-off: replace the repeated "many coins" stock photo on several
already-posted Fresh Live messages, identified by the user via message
links. The bot can't read a message's existing caption back from Telegram
(there's no read-only API for that - editing is the only way to touch a
message, and that always writes), so each replacement image is picked
from a short topic hint the user gave in chat rather than the post's
actual text."""

import json
import os

import requests

from stock_image import find_stock_image

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN_2"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID_2"]
IMAGE_HISTORY_FILE = os.environ.get("IMAGE_HISTORY_FILE") or "data/seen_ids_channel_images.json"

# message_id -> short English hint for picking a relevant replacement photo.
TARGETS = {
    56: "Ireland flag crypto regulation government",
    50: "counterfeit fake token scam warning",
    48: "hardware crypto wallet device security",
    44: "business companies corporate office buildings",
    41: "gold bars bullion vault",
    35: "cryptocurrency market chart analysis",
    29: "blockchain technology network digital",
}

for message_id, title_hint in TARGETS.items():
    image_url = find_stock_image(title_hint, history_path=IMAGE_HISTORY_FILE)
    if not image_url:
        print(f"{message_id}: could not find a replacement image, skipped.")
        continue

    resp = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageMedia",
        data={
            "chat_id": CHAT_ID,
            "message_id": message_id,
            "media": json.dumps({"type": "photo", "media": image_url}),
        },
        timeout=30,
    )
    result = resp.json()
    print(f"{message_id} ({title_hint!r}): {result}")
