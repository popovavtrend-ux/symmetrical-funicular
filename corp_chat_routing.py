import json
import re

from corp_chat_ai import generate_reply

ROUTING_PROMPT_TEMPLATE = (
    "Ты диспетчер общего рабочего чата компании в Telegram. {company}\n\n"
    "Состав чата (роли и зона ответственности):\n{roster}\n\n"
    "Контекст последних сообщений в чате (от старых к новым):\n{history}\n\n"
    "Последнее сообщение от руководителя компании: \"{text}\"\n\n"
    "Определи, кто из команды должен на него отреагировать. Обычно это "
    "1-2 человека по своей компетенции. Если сообщение не требует ответа "
    "(реплика, статус, \"спасибо\" и т.п.) - никто не отвечает. Изредка "
    "уместно больше, если вопрос затрагивает несколько областей. Один "
    "человек - основной ответчик (\"primary\"), другие могут коротко "
    "дополнить (\"secondary\"), не подменяя основного.\n\n"
    "Ответь СТРОГО в виде JSON без пояснений, например:\n"
    '{{"respond": [{{"key": "accountant", "priority": "primary"}}, '
    '{{"key": "lawyer", "priority": "secondary"}}]}}\n'
    "Используй только ключи (key) из списка состава чата выше, ровно как они написаны."
)


def route_message(company_description, roster_text, history_text, text, provider, model):
    prompt = ROUTING_PROMPT_TEMPLATE.format(
        company=company_description, roster=roster_text, history=history_text, text=text
    )
    try:
        raw = generate_reply(provider, model, "Ты возвращаешь только валидный JSON, без markdown и пояснений.", prompt, max_tokens=300)
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(match.group(0) if match else raw)
        respond = data.get("respond") or []
        return [(item["key"], item.get("priority") or "primary") for item in respond if item.get("key")]
    except Exception as e:
        print(f"Routing failed, no one will auto-reply to this message: {e}")
        return []
