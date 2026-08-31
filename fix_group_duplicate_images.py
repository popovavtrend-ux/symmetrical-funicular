"""One-off: replace repeated stock photos on a batch of already-posted
Cryptocompass group messages (identified by the user via message links).
No topic hint was given this time, so each gets a distinct generic
crypto/finance query rather than a per-post match - the anti-repeat
history (shared with the live pipeline) still guarantees no two of these,
or of future posts, get the same photo again."""

import json
import os
import time

import requests

from stock_image import find_stock_image

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
IMAGE_HISTORY_FILE = os.environ.get("IMAGE_HISTORY_FILE") or "data/seen_ids_images.json"

# First pass (154-189, 245-264) already succeeded; these 13 hit Telegram's
# edit-flood limit (~20/min to the same chat) and got 429s.
MESSAGE_IDS = sorted({191, 194, 198, 202, 205, 210, 218, 229, 232, 235, 238, 241, 243})

QUERY_ROTATION = [
    "bitcoin coin gold",
    "ethereum blockchain digital",
    "cryptocurrency trading chart",
    "stock market finance",
    "digital wallet technology",
    "blockchain network global",
    "financial technology innovation",
    "crypto exchange trading screen",
    "gold bars investment",
    "banking finance building",
    "mobile payment technology",
    "data center servers",
    "regulation law government",
    "business meeting negotiation",
    "world economy globe",
    "security cybersecurity lock",
    "startup technology office",
    "investment growth chart",
]

for i, message_id in enumerate(MESSAGE_IDS):
    title_hint = QUERY_ROTATION[i % len(QUERY_ROTATION)]
    image_url = find_stock_image(title_hint, history_path=IMAGE_HISTORY_FILE)
    if not image_url:
        print(f"{message_id}: could not find a replacement image, skipped.")
        continue

    for attempt in range(4):
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
        if result.get("ok") or result.get("error_code") != 429:
            break
        wait = result.get("parameters", {}).get("retry_after", 5) + 1
        print(f"{message_id}: rate-limited, waiting {wait}s before retry {attempt + 1}/3")
        time.sleep(wait)

    print(f"{message_id} ({title_hint!r}): ok={result.get('ok')} {'' if result.get('ok') else result}")
    time.sleep(3.5)
