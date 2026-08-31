import json
import os
import time

from corp_chat_ai import generate_reply
from corp_chat_config import CHAT_ID, HISTORY_LIMIT, PERSONAS
from telegram_chat import get_me, get_updates, send_text

STATE_FILE = os.environ.get("CORP_CHAT_STATE_FILE") or "data/corp_chat_state.json"

TELEGRAM_MAX_LEN = 4096

SYSTEM_PROMPT_TEMPLATE = (
    "Ты — {name}, {role}. Ты участник общего корпоративного группового чата "
    "в Telegram вместе с руководителем компании и другими коллегами.\n\n"
    "Пиши как обычный человек в мессенджере: коротко, по делу, простым "
    "деловым языком, без канцелярита и без markdown-разметки. Не повторяй "
    "то, что уже написали другие участники чата, а дополняй своей позицией "
    "по своей части вопроса. Если вопрос явно не по твоей части — можно "
    "коротко это отметить и не лезть в чужую область. Если для точного "
    "ответа не хватает данных (документов, сумм, дат) — прямо спроси, чего "
    "не хватает, вместо того чтобы гадать.\n\n"
    "Помни: ты — ИИ-ассистент, играющий роль сотрудника, а не аттестованный "
    "специалист. Если вопрос серьёзный и решение по нему может стоить "
    "компании денег или иметь юридические последствия, мягко предупреди, "
    "что финальное решение стоит сверить с живым специалистом — но не делай "
    "это в каждом сообщении, только когда это действительно важно.\n\n"
    "История переписки в чате (от старых сообщений к новым):\n{history}"
)


def load_corp_state(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {"last_update_id": data.get("last_update_id", 0), "history": data.get("history", [])}


def save_corp_state(path, state):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def resolve_persona_runtime(persona):
    token = os.environ.get(persona["token_env"])
    if not token:
        return None
    info = get_me(token)
    return {
        **persona,
        "token": token,
        "bot_id": info["id"],
        "username": (info.get("username") or "").lower(),
    }


def format_history(history):
    return "\n".join(f"{item['name']}: {item['text']}" for item in history) or "(пока пусто)"


def find_target_personas(message_text, reply_to_bot_id, personas):
    if reply_to_bot_id is not None:
        matches = [p for p in personas if p["bot_id"] == reply_to_bot_id]
        if matches:
            return matches
    lowered = (message_text or "").lower()
    mentioned = [p for p in personas if p["username"] and f"@{p['username']}" in lowered]
    if mentioned:
        return mentioned
    return personas


def main():
    personas = [p for p in (resolve_persona_runtime(p) for p in PERSONAS) if p]
    if not personas:
        print("No persona bot tokens configured (TELEGRAM_BOT_TOKEN_LAWYER / "
              "TELEGRAM_BOT_TOKEN_ACCOUNTANT), nothing to do.")
        return
    if not CHAT_ID:
        raise RuntimeError("TELEGRAM_CHAT_ID_CORP (or TELEGRAM_CHAT_ID) is not set")

    is_first_run = not os.path.exists(STATE_FILE)
    state = load_corp_state(STATE_FILE) or {"last_update_id": 0, "history": []}

    # Any of the persona bots can read updates as long as it has privacy
    # mode disabled in BotFather - we just need one to see the group.
    listener_token = personas[0]["token"]
    offset = state["last_update_id"] + 1 if state["last_update_id"] else None
    updates = get_updates(listener_token, offset=offset)
    if not updates:
        print("No new updates.")
        return

    if is_first_run:
        # Don't answer whatever backlog is already sitting in the group when
        # the bots are first turned on - just seed the offset.
        max_update_id = max(u["update_id"] for u in updates)
        save_corp_state(STATE_FILE, {"last_update_id": max_update_id, "history": []})
        print(f"First run: seeded update_id={max_update_id}, no replies sent.")
        return

    bot_ids = {p["bot_id"] for p in personas}
    history = state["history"]
    max_update_id = state["last_update_id"]

    for update in updates:
        max_update_id = max(max_update_id, update["update_id"])
        message = update.get("message")
        if not message:
            continue
        if str(message.get("chat", {}).get("id")) != str(CHAT_ID):
            continue
        text = message.get("text")
        if not text:
            continue
        sender = message.get("from", {})
        if sender.get("id") in bot_ids:
            continue  # our own personas don't reply to each other

        sender_name = sender.get("first_name") or sender.get("username") or "Коллега"
        history.append({"name": sender_name, "text": text})

        reply_to = message.get("reply_to_message") or {}
        reply_to_bot_id = (reply_to.get("from") or {}).get("id")
        targets = find_target_personas(text, reply_to_bot_id, personas)

        for persona in targets:
            try:
                system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
                    name=persona["display_name"],
                    role=persona["role_description"],
                    history=format_history(history[-HISTORY_LIMIT:]),
                )
                reply = generate_reply(
                    persona["provider"],
                    persona["model"],
                    system_prompt,
                    f"Ответь в чате как {persona['display_name']} на последнее сообщение выше.",
                )
                reply = reply[:TELEGRAM_MAX_LEN]
                send_text(persona["token"], CHAT_ID, reply)
                history.append({"name": persona["display_name"], "text": reply})
                time.sleep(2)
            except Exception as e:
                print(f"Failed to get/send reply from {persona['display_name']}: {e}")
                continue

    save_corp_state(STATE_FILE, {"last_update_id": max_update_id, "history": history[-HISTORY_LIMIT:]})


if __name__ == "__main__":
    main()
