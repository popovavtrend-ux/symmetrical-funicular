import json
import os

from education_topics import TOPICS
from main import build_message
from stock_image import find_stock_image
from telegram_post import send_message, send_photo
from translate import explain_topic

STATE_FILE = os.environ.get("EDUCATION_STATE_FILE") or "data/education_state.json"
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

TELEGRAM_PHOTO_CAPTION_MAX_LEN = 1024


def load_posted_topics():
    if not os.path.exists(STATE_FILE):
        return []
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)["posted_topics"]


def save_posted_topics(posted_topics):
    os.makedirs(os.path.dirname(STATE_FILE) or ".", exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"posted_topics": posted_topics}, f, ensure_ascii=False, indent=2)


def next_topic(posted_topics):
    for topic in TOPICS:
        if topic not in posted_topics:
            return topic
    # Cycled through every topic - start over from the beginning.
    return TOPICS[0]


def main():
    posted_topics = load_posted_topics()
    topic = next_topic(posted_topics)

    title, explanation = explain_topic(topic)
    image_url = find_stock_image(title)

    if image_url:
        caption = build_message(title, explanation, max_len=TELEGRAM_PHOTO_CAPTION_MAX_LEN)
        try:
            send_photo(BOT_TOKEN, CHAT_ID, image_url, caption)
        except Exception as e:
            print(f"Failed to send photo ({image_url!r}), falling back to text: {e}")
            send_message(BOT_TOKEN, CHAT_ID, build_message(title, explanation))
    else:
        send_message(BOT_TOKEN, CHAT_ID, build_message(title, explanation))

    if topic in posted_topics:
        posted_topics = [topic]  # cycled back to the start - restart the list
    else:
        posted_topics = posted_topics + [topic]
    save_posted_topics(posted_topics)
    print(f"Posted educational topic: {topic!r} -> {title!r}")


if __name__ == "__main__":
    main()
