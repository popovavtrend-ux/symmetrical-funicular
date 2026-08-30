import os

from fetch_feed import fetch_entries
from main import FEED_URLS, build_message, clean_summary
from telegram_post import send_message
from translate import translate

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
COUNT = int(os.environ.get("TEST_POST_COUNT") or "2")

entries = fetch_entries(FEED_URLS)[:COUNT]

for entry in entries:
    title = entry.title
    summary = clean_summary(entry)
    title_ru, summary_ru = translate(title, summary)
    message = build_message(title_ru, summary_ru)
    send_message(BOT_TOKEN, CHAT_ID, message)
    print(f"[TEST] Posted: {title!r} -> {title_ru!r}")
