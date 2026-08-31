import json
import os
import random
import time

from corp_chat_ai import generate_file_task_result, generate_reply
from corp_chat_config import (
    ACCESS_AUTHORITY,
    CHAT_ID,
    CLAUDE_DEFAULT_MODEL,
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
from corp_chat_access import (
    grant_access,
    has_access,
    looks_like_grant,
    register_access_request,
    register_file_message,
    resolve_reply_target,
)
from corp_chat_files import build_html, build_pptx, build_xlsx, extract_attachment
from corp_chat_routing import route_message
from telegram_chat import download_file_bytes, get_me, get_updates, send_document, send_text

STATE_FILE = os.environ.get("CORP_CHAT_STATE_FILE") or "data/corp_chat_state.json"
TELEGRAM_MAX_LEN = 4096

# How long an uploaded file with no accompanying instruction waits around
# for a follow-up message ("сделай на основе этого...") before being
# forgotten. We only ever keep file_ids (cheap), never the file bytes
# themselves, across runs - so this is safe to persist in git-tracked state.
UPLOAD_BUFFER_TTL_SEC = int(os.environ.get("CORP_CHAT_UPLOAD_TTL_SEC") or str(20 * 60))
MAX_BUFFERED_UPLOADS = 6

SYSTEM_PROMPT_TEMPLATE = (
    "Ты — {name}, сотрудник компании. {company}\n\n"
    "Твоя роль в команде: {role}.\n\n"
    "Ты участник общего рабочего группового чата в Telegram вместе с "
    "руководителем компании и остальной командой:\n{roster}\n\n"
    "Пиши как живой человек в рабочем чате: коротко, по делу, простым "
    "деловым языком, без канцелярита и без markdown-разметки. Отвечай в "
    "рамках своей компетенции; если вопрос немного затрагивает и чужую "
    "область — можно коротко добавить свою реплику, не подменяя коллегу.\n\n"
    "Никогда, ни при каких обстоятельствах не упоминай и не намекай, что ты "
    "ИИ, языковая модель, бот, ассистент или что ты кого-то \"изображаешь\"/"
    "\"играешь роль\" — даже если тебя прямо об этом спросят в чате. Ты — "
    "{name}, и всё. Если для точного ответа не хватает данных (документов, "
    "сумм, дат) или ты в чём-то не уверен — спроси или оговорись об этом "
    "так, как это сделал бы живой коллега (\"уточню и отпишусь\", \"надо "
    "свериться с договором/1С, скажу точнее чуть позже\", \"тут лучше по "
    "документам смотреть, на глаз не готов утверждать\"), а не как ассистент, "
    "которому не хватает вводных для выполнения запроса.\n\n"
    "У тебя нет доступа ни к каким реальным базам, системам и документам "
    "компании — только к тому, что реально прислали в этот чат (текстом или "
    "файлом) выше. Если просят выдать конкретные закрытые данные, которых "
    "здесь нет (например, \"скинь выписку по счёту за месяц\", реальные "
    "суммы, персональные данные сотрудников и т.п.) — НИКОГДА не выдумывай "
    "цифры и не изображай, что это у тебя под рукой. По-человечески скажи, "
    "что сейчас этого нет с собой / нет доступа, и что нужно уточнить у "
    "{authority} — либо попроси прислать нужный документ в чат, чтобы "
    "посчитать уже по нему.\n\n"
    "Файл, который кто-то присылает в этот чат, принадлежит именно ему — "
    "остальные (включая тебя) не открывают и не пересказывают его содержимое "
    "без явного \"да, доступ даю\" от приславшего в ответ на просьбу. Если "
    "видишь в переписке, что кто-то просит доступ к чужому файлу, а хозяин "
    "файла ещё не подтвердил — не пересказывай, что в файле, и не работай "
    "с ним; по-человечески скажи, что это не твой файл и решать не тебе, "
    "ждём подтверждения от того, кто его прислал.\n\n"
    "История переписки в чате (от старых сообщений к новым):\n{history}"
)

FILE_TASK_SYSTEM_SUFFIX = (
    "\n\nСейчас тебе также прислали файл(ы) с конкретной задачей (сводная "
    "таблица, заполнить/пересчитать таблицу или коммерческое предложение, "
    "презентация, html-страница и т.п.) — файлы приложены ниже. Выполни "
    "задачу и верни результат через инструмент deliver_result: если по "
    "задаче нужен файл — kind='table' (таблица/сводная/пересчёт, уйдёт как "
    "xlsx), 'html' (html-файл) или 'slides' (презентация, уйдёт как pptx); "
    "если файл не нужен — kind='none' и просто ответь текстом."
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
        "uploads": data.get("uploads", {}),
        "file_owners": data.get("file_owners", {}),
        "file_messages": data.get("file_messages", {}),
        "access_requests": data.get("access_requests", {}),
        "grants": data.get("grants", {}),
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


def message_attachments(message):
    atts = []
    doc = message.get("document")
    if doc:
        atts.append({"file_id": doc["file_id"], "file_name": doc.get("file_name") or "file", "mime_type": doc.get("mime_type") or ""})
    photos = message.get("photo")
    if photos:
        best = photos[-1]  # Telegram lists photo sizes smallest first
        atts.append({"file_id": best["file_id"], "file_name": "photo.jpg", "mime_type": "image/jpeg"})
    return atts


def find_targets(text, reply_to_bot_id, personas, roster_text, history, attachments=None):
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

    routing_text = text or ""
    if attachments:
        names = ", ".join(a.get("file_name") or "файл" for a in attachments)
        routing_text += f"\n[К сообщению приложены файлы: {names}]"
    return route_message(
        COMPANY_DESCRIPTION, roster_text, format_history(history[-15:]), routing_text, ROUTING_PROVIDER, ROUTING_MODEL
    )


def build_reply(persona, roster_text, history):
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        name=persona["display_name"],
        company=COMPANY_DESCRIPTION,
        role=persona["role_description"],
        roster=roster_text,
        authority=ACCESS_AUTHORITY,
        history=format_history(history[-HISTORY_LIMIT:]),
    )
    reply = generate_reply(
        persona["provider"],
        persona["model"],
        system_prompt,
        f"Ответь в чате как {persona['display_name']} на последнее сообщение выше.",
    )
    return reply[:TELEGRAM_MAX_LEN]


def build_file_task_reply(persona, item, roster_text, history):
    downloaded = []
    for att in item["attachments"]:
        try:
            file_bytes = download_file_bytes(persona["token"], att["file_id"])
            downloaded.append(extract_attachment(file_bytes, att.get("file_name"), att.get("mime_type")))
        except Exception as e:
            downloaded.append({"kind": "unsupported", "text": f"(не удалось скачать файл {att.get('file_name')}: {e})"})

    system_prompt = (
        SYSTEM_PROMPT_TEMPLATE.format(
            name=persona["display_name"],
            company=COMPANY_DESCRIPTION,
            role=persona["role_description"],
            roster=roster_text,
            authority=ACCESS_AUTHORITY,
            history=format_history(history[-HISTORY_LIMIT:]),
        )
        + FILE_TASK_SYSTEM_SUFFIX
    )
    result = generate_file_task_result(CLAUDE_DEFAULT_MODEL, system_prompt, item.get("instruction"), downloaded)
    message_text = (result.get("message") or "Готово.")[:TELEGRAM_MAX_LEN]
    output = result.get("output") or {"kind": "none"}
    kind = output.get("kind")

    if kind == "table":
        filename = _with_ext(output.get("filename"), "result.xlsx", ".xlsx")
        return message_text, (filename, build_xlsx(output.get("table") or {}))
    if kind == "html":
        filename = _with_ext(output.get("filename"), "result.html", ".html")
        return message_text, (filename, build_html(output.get("html")))
    if kind == "slides":
        filename = _with_ext(output.get("filename"), "result.pptx", ".pptx")
        return message_text, (filename, build_pptx(output.get("slides") or []))
    return message_text, None


def _with_ext(filename, default, ext):
    filename = (filename or default).strip()
    return filename if filename.lower().endswith(ext) else filename + ext


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

    empty_state = {
        "last_update_id": 0,
        "history": [],
        "pending": [],
        "uploads": {},
        "file_owners": {},
        "file_messages": {},
        "access_requests": {},
        "grants": {},
    }

    is_first_run = not os.path.exists(STATE_FILE)
    state = load_corp_state(STATE_FILE) or empty_state

    # Any persona bot with privacy mode disabled can read the group's
    # updates - we just need one of them to poll with.
    listener_token = personas[0]["token"]
    offset = state["last_update_id"] + 1 if state["last_update_id"] else None
    updates = get_updates(listener_token, offset=offset)

    if is_first_run:
        if updates:
            max_update_id = max(u["update_id"] for u in updates)
            save_corp_state(STATE_FILE, {**empty_state, "last_update_id": max_update_id})
            print(f"First run: seeded update_id={max_update_id}, no replies sent.")
        else:
            print("First run: no updates yet, nothing to seed.")
        return

    history = state["history"]
    pending = state["pending"]
    uploads = state["uploads"]
    file_owners = state["file_owners"]
    file_messages = state["file_messages"]
    access_requests = state["access_requests"]
    grants = state["grants"]
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
            if item.get("attachments"):
                reply_text, output_file = build_file_task_reply(persona, item, roster_text, history)
                if output_file:
                    filename, file_bytes = output_file
                    send_document(persona["token"], CHAT_ID, filename, file_bytes, caption=reply_text)
                    history.append({"name": persona["display_name"], "text": f"{reply_text} [файл: {filename}]"})
                else:
                    send_text(persona["token"], CHAT_ID, reply_text)
                    history.append({"name": persona["display_name"], "text": reply_text})
            else:
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
        sender = message.get("from", {})
        if sender.get("id") in bot_ids:
            continue  # our own personas don't reply to each other

        sender_name = sender.get("first_name") or sender.get("username") or "Коллега"
        sender_key = str(sender.get("id"))
        text = message.get("text") or message.get("caption")
        attachments = message_attachments(message)
        reply_to = message.get("reply_to_message") or {}
        reply_to_id = str(reply_to["message_id"]) if reply_to.get("message_id") else None

        # Whoever sends a file owns it, regardless of whether this message
        # ends up buffered or answered right away.
        register_file_message(file_owners, file_messages, message["message_id"], attachments, sender_key, sender_name)

        if attachments and not text:
            # A bare upload with no instruction yet - hold onto it and wait
            # for the follow-up message that says what to do with it.
            bucket = [u for u in uploads.get(sender_key, []) if now - u["ts"] < UPLOAD_BUFFER_TTL_SEC]
            bucket.extend({**a, "ts": now} for a in attachments)
            uploads[sender_key] = bucket[-MAX_BUFFERED_UPLOADS:]
            history.append({"name": sender_name, "text": "[прислал(а) файл]"})
            continue

        if not text:
            continue  # nothing to react to (e.g. a sticker)

        history.append({"name": sender_name, "text": text})

        buffered = [u for u in uploads.pop(sender_key, []) if now - u["ts"] < UPLOAD_BUFFER_TTL_SEC]
        all_attachments = buffered + attachments

        # Replying to someone else's file: either you already have access
        # (attach it), you're the owner replying in your own thread (always
        # allowed, and a "да, доступ даю"-style reply unlocks it for whoever
        # asked), or you don't have access yet (blocked - and this message
        # itself becomes the recorded request).
        foreign_atts, foreign_owner = resolve_reply_target(reply_to_id, file_messages, access_requests, file_owners)
        if foreign_atts and foreign_owner:
            if foreign_owner == sender_key:
                if looks_like_grant(text, reply_is_direct_request=reply_to_id in access_requests):
                    grant_access(grants, access_requests, sender_key, foreign_atts, reply_to_id)
                all_attachments = all_attachments + foreign_atts
            elif has_access(grants, foreign_owner, sender_key, foreign_atts):
                all_attachments = all_attachments + foreign_atts
            else:
                register_access_request(access_requests, message["message_id"], foreign_atts, sender_key, foreign_owner)

        reply_to_bot_id = (reply_to.get("from") or {}).get("id")
        targets = find_targets(text, reply_to_bot_id, personas, roster_text, history, attachments=all_attachments)

        for key, priority in targets:
            if key not in personas_by_key:
                continue
            pending.append(
                {
                    "persona_key": key,
                    "priority": priority,
                    "due_at": compute_due_at(time.time(), priority),
                    "attachments": all_attachments or None,
                    "instruction": text if all_attachments else None,
                }
            )

    save_corp_state(
        STATE_FILE,
        {
            "last_update_id": max_update_id,
            "history": history[-HISTORY_LIMIT:],
            "pending": pending,
            "uploads": uploads,
            "file_owners": file_owners,
            "file_messages": file_messages,
            "access_requests": access_requests,
            "grants": grants,
        },
    )


if __name__ == "__main__":
    main()
