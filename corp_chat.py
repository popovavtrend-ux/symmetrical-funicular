import json
import os
import random
import time

from corp_chat_ai import generate_reply
from corp_chat_config import (
    CHAT_ID,
    COMPANY_DESCRIPTION,
    HISTORY_LIMIT,
    MAX_REPLY_DELAY_SEC,
    MIN_REPLY_DELAY_SEC,
    PERSONAS,
    ROUTING_MODEL,
    ROUTING_PROVIDER,
    SECONDARY_EXTRA_DELAY_SEC,
    team_roster_text,
)
from corp_chat_routing import route_message
from telegram_chat import get_me, get_updates, send_text

STATE_FILE = os.environ.get("CORP_CHAT_STATE_FILE") or "data/corp_chat_state.json"
TELEGRAM_MAX_LEN = 4096

SYSTEM_PROMPT_TEMPLATE = (
    "Ты — {name}, сотрудник компании. {company}\n\n"
    "Твоя роль в команде: {role}.\n\n"
    "Ты участник общего рабочего группового чата в Telegram вместе с "
    "руководителем компании и остальной командой:\n{roster}\n\n"
    "Пиши как обычный человек в мессенджере: коротко, по делу, простым "
    "деловым языком, без канцелярита и без markdown-разметки. Отвечай в "
    "рамках своей компетенции; если вопрос немного затрагивает и чужую "
    "область — можно коротко добавить свою реплику, не подменяя коллегу. "
    "Если для точного ответа не хватает данных (документов, сумм, дат) — "
    "прямо спроси, чего не хватает, вместо того чтобы гадать.\n\n"
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
    return {
        "last_update_id": data.get("last_update_id", 0),
        "history": data.get("history", []),
        "pending": data.get("pending", []),
    }


def save_corp_state(path, state):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def resolve_persona_runtime(persona):
    token = os.environ.get(persona["token_env"])
    if not token:
        return None
    info = get_me(token)
    return {**persona, "token": token, "bot_id": info["id"], "username": (info.get("username") or "").lower()}


def format_history(history):
    return "\n".join(f"{item['name']}: {item['text']}" for item in history) or "(пока пусто)"


def compute_due_at(now, priority):
    base = random.randint(MIN_REPLY_DELAY_SEC, MAX_REPLY_DELAY_SEC)
    if priority == "secondary":
        base += random.randint(0, SECONDARY_EXTRA_DELAY_SEC)
    return now + base


def find_targets(text, reply_to_bot_id, personas, roster_text, history):
    # An explicit @mention or a reply-to-bot always wins over automatic
    # routing - if you address someone directly, they answer, full stop.
    if reply_to_bot_id is not None:
        matches = [(p["key"], "primary") for p in personas if p["bot_id"] == reply_to_bot_id]
        if matches:
            return matches
    lowered = (text or "").lower()
    mentioned = [(p["key"], "primary") for p in personas if p["username"] and f"@{p['username']}" in lowered]
    if mentioned:
        return mentioned
    return route_message(
        COMPANY_DESCRIPTION, roster_text, format_history(history[-15:]), text, ROUTING_PROVIDER, ROUTING_MODEL
    )


def build_reply(persona, roster_text, history):
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        name=persona["display_name"],
        company=COMPANY_DESCRIPTION,
        role=persona["role_description"],
        roster=roster_text,
        history=format_history(history[-HISTORY_LIMIT:]),
    )
    reply = generate_reply(
        persona["provider"],
        persona["model"],
        system_prompt,
        f"Ответь в чате как {persona['display_name']} на последнее сообщение выше.",
    )
    return reply[:TELEGRAM_MAX_LEN]


def main():
    personas = [p for p in (resolve_persona_runtime(p) for p in PERSONAS) if p]
    if not personas:
        print(
            "No persona bot tokens configured (see team.json for the expected "
            "TELEGRAM_BOT_TOKEN_* secret names), nothing to do."
        )
        return
    if not CHAT_ID:
        raise RuntimeError("TELEGRAM_CHAT_ID_CORP (or TELEGRAM_CHAT_ID) is not set")

    personas_by_key = {p["key"]: p for p in personas}
    bot_ids = {p["bot_id"] for p in personas}
    roster_text = team_roster_text(personas)

    is_first_run = not os.path.exists(STATE_FILE)
    state = load_corp_state(STATE_FILE) or {"last_update_id": 0, "history": [], "pending": []}

    # Any persona bot with privacy mode disabled can read the group's
    # updates - we just need one of them to poll with.
    listener_token = personas[0]["token"]
    offset = state["last_update_id"] + 1 if state["last_update_id"] else None
    updates = get_updates(listener_token, offset=offset)

    if is_first_run:
        if updates:
            max_update_id = max(u["update_id"] for u in updates)
            save_corp_state(STATE_FILE, {"last_update_id": max_update_id, "history": [], "pending": []})
            print(f"First run: seeded update_id={max_update_id}, no replies sent.")
        else:
            print("First run: no updates yet, nothing to seed.")
        return

    history = state["history"]
    pending = state["pending"]
    max_update_id = state["last_update_id"]

    # 1) Send whatever scheduled replies have come due since the last poll.
    # This - not the poll interval - is what actually paces the chat: a
    # colleague who "saw" the message a while ago and is only now getting
    # back to it, instead of an instant bot reply.
    now = time.time()
    still_pending = []
    for item in pending:
        if item["due_at"] > now:
            still_pending.append(item)
            continue
        persona = personas_by_key.get(item["persona_key"])
        if not persona:
            continue
        try:
            reply = build_reply(persona, roster_text, history)
            send_text(persona["token"], CHAT_ID, reply)
            history.append({"name": persona["display_name"], "text": reply})
            time.sleep(random.uniform(1, 3))
        except Exception as e:
            print(f"Failed to send scheduled reply from {persona['display_name']}: {e}")
    pending = still_pending

    # 2) Ingest new human messages and schedule (not send yet) replies.
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
        targets = find_targets(text, reply_to_bot_id, personas, roster_text, history)

        for key, priority in targets:
            if key not in personas_by_key:
                continue
            pending.append(
                {
                    "persona_key": key,
                    "priority": priority,
                    "due_at": compute_due_at(time.time(), priority),
                }
            )

    save_corp_state(
        STATE_FILE,
        {"last_update_id": max_update_id, "history": history[-HISTORY_LIMIT:], "pending": pending},
    )


if __name__ == "__main__":
    main()
