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

# Sent once and pinned - the "welcome" a new subscriber sees at the top of
# the channel, spelling out what's actually here (unlike the description,
# which most people never open).
PINNED_MESSAGE = (
    "👋 Добро пожаловать!\n\n"
    "<b>Fresh Live</b> — крипто-новости и объяснения простым языком, без "
    "хайпа и финансовых советов.\n\n"
    "Что здесь есть:\n"
    "💭 Новости с личным мнением\n"
    "📘 Развёрнутые объяснения для тех, кто только начинает разбираться\n"
    "🌐 Обзор рынка каждое утро в 8:00\n"
    "📚 Обучающие посты по крипто-терминам — по кругу\n\n"
    "Каждая новость — со ссылкой на первоисточник."
)


def set_description():
    resp = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/setChatDescription",
        data={"chat_id": CHAT_ID, "description": DESCRIPTION},
        timeout=30,
    )
    print("setChatDescription:", resp.json())


def send_and_pin_welcome_message():
    resp = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={
            "chat_id": CHAT_ID,
            "text": PINNED_MESSAGE,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=30,
    )
    result = resp.json()
    print("sendMessage:", result)
    if not result.get("ok"):
        return

    message_id = result["result"]["message_id"]
    pin_resp = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/pinChatMessage",
        data={"chat_id": CHAT_ID, "message_id": message_id, "disable_notification": True},
        timeout=30,
    )
    print("pinChatMessage:", pin_resp.json())


if __name__ == "__main__":
    set_description()
    send_and_pin_welcome_message()
