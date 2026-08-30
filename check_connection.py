import os

from telegram_post import send_message

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

resp = send_message(BOT_TOKEN, CHAT_ID, "Тест соединения бота с каналом.")
print("OK:", resp.get("result", {}).get("chat", {}))
