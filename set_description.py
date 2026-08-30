import os

import requests

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN_2"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID_2"]
DESCRIPTION = (
    "Fresh Live — крипта и всё, что на неё влияет, простыми словами. "
    "Новости с разбором и объяснением терминов + обучающие посты для "
    "новичков. Никаких финансовых советов — только понятная информация "
    "для всех: от школьника до пенсионера."
)

resp = requests.post(
    f"https://api.telegram.org/bot{BOT_TOKEN}/setChatDescription",
    data={"chat_id": CHAT_ID, "description": DESCRIPTION},
    timeout=30,
)
print(resp.json())
