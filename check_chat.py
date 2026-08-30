import os

import requests

bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
chat_id = os.environ["TELEGRAM_CHAT_ID"]

resp = requests.get(
    f"https://api.telegram.org/bot{bot_token}/getChat",
    params={"chat_id": chat_id},
    timeout=30,
)
print(f"getChat status={resp.status_code}")
print(resp.text)

resp2 = requests.get(f"https://api.telegram.org/bot{bot_token}/getMe", timeout=30)
print(f"getMe status={resp2.status_code}")
print(resp2.text)
