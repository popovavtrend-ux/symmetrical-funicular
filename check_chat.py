import os

import requests

bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
chat_id = os.environ["TELEGRAM_CHAT_ID"]

for candidate in (chat_id, "@cryptocompass_news"):
    resp = requests.get(
        f"https://api.telegram.org/bot{bot_token}/getChat",
        params={"chat_id": candidate},
        timeout=30,
    )
    print(f"getChat({candidate!r}) status={resp.status_code}")
    print(resp.text)

resp2 = requests.get(f"https://api.telegram.org/bot{bot_token}/getMe", timeout=30)
print(f"getMe status={resp2.status_code}")
print(resp2.text)
bot_id = resp2.json()["result"]["id"]

resp3 = requests.get(
    f"https://api.telegram.org/bot{bot_token}/getChatMember",
    params={"chat_id": "@cryptocompass_news", "user_id": bot_id},
    timeout=30,
)
print(f"getChatMember status={resp3.status_code}")
print(resp3.text)
