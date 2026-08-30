import os

from fetch_feed import fetch_entries
from main import FEED_URLS, build_message, clean_summary, extract_image_url, get_source_name
from telegram_post import send_message, send_photo
from translate import translate

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
COUNT = int(os.environ.get("TEST_POST_COUNT") or "2")

entries = fetch_entries(FEED_URLS)[:COUNT]

for entry in entries:
    title = entry.title
    summary = clean_summary(entry)
    image_url = extract_image_url(entry)
    source_name = get_source_name(entry)
    title_ru, summary_ru = translate(title, summary)

    if image_url:
        caption = build_message(title_ru, summary_ru, source_name=source_name, max_len=1024)
        try:
            send_photo(BOT_TOKEN, CHAT_ID, image_url, caption)
            print(f"[TEST] Posted photo (image={image_url!r}): {title!r} -> {title_ru!r}")
            continue
        except Exception as e:
            print(f"[TEST] Photo send failed ({e}), falling back to text")

    message = build_message(title_ru, summary_ru, source_name=source_name)
    send_message(BOT_TOKEN, CHAT_ID, message)
    print(f"[TEST] Posted text (no image): {title!r} -> {title_ru!r}")
