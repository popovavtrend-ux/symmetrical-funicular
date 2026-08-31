import os


def _anthropic_reply(model, system_prompt, user_prompt, max_tokens):
    from anthropic_client import get_client

    client = get_client()
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return resp.content[0].text.strip()


def _deepseek_reply(model, system_prompt, user_prompt, max_tokens):
    import requests

    resp = requests.post(
        "https://api.deepseek.com/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens,
        },
        timeout=60,
    )
    if not resp.ok:
        raise RuntimeError(f"DeepSeek API error {resp.status_code}: {resp.text}")
    return resp.json()["choices"][0]["message"]["content"].strip()


def generate_reply(provider, model, system_prompt, user_prompt, max_tokens=500):
    if provider == "deepseek":
        return _deepseek_reply(model, system_prompt, user_prompt, max_tokens)
    return _anthropic_reply(model, system_prompt, user_prompt, max_tokens)


# File tasks ("сделай таблицу", "пересчитай КП", "сделай презентацию", ...)
# always go through Claude via tool use, regardless of the persona's normal
# text-reply provider - forcing a structured result reliably (vs. asking
# DeepSeek to hand back parseable JSON) matters more here than provider choice.
FILE_TASK_TOOL = {
    "name": "deliver_result",
    "description": "Отдать результат выполненной задачи в чат: короткое сообщение и, если нужно, готовый файл.",
    "input_schema": {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "Короткое сообщение в чат в стиле обычного человека - что сделано / что не так.",
            },
            "output": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["none", "table", "html", "slides"],
                        "description": (
                            "none - файл не нужен, достаточно текста. table - таблица/сводная "
                            "таблица/пересчитанный документ (уйдёт как .xlsx). html - произвольный "
                            "html-файл. slides - презентация (уйдёт как .pptx)."
                        ),
                    },
                    "filename": {"type": "string", "description": "Имя файла без учёта расширения."},
                    "table": {
                        "type": "object",
                        "properties": {
                            "sheet_name": {"type": "string"},
                            "headers": {"type": "array", "items": {"type": "string"}},
                            "rows": {"type": "array", "items": {"type": "array"}},
                        },
                    },
                    "html": {"type": "string"},
                    "slides": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "bullets": {"type": "array", "items": {"type": "string"}},
                            },
                        },
                    },
                },
                "required": ["kind"],
            },
        },
        "required": ["message", "output"],
    },
}


def generate_file_task_result(model, system_prompt, instruction_text, attachments):
    from anthropic_client import get_client

    client = get_client()
    content = [{"type": "text", "text": instruction_text or "(без текста, см. приложенные файлы)"}]
    for att in attachments:
        if att["kind"] == "pdf":
            content.append(
                {"type": "document", "source": {"type": "base64", "media_type": att["media_type"], "data": att["data"]}}
            )
        elif att["kind"] == "image":
            content.append(
                {"type": "image", "source": {"type": "base64", "media_type": att["media_type"], "data": att["data"]}}
            )
        else:
            content.append({"type": "text", "text": f"Содержимое файла:\n{att['text']}"})

    resp = client.messages.create(
        model=model,
        max_tokens=4000,
        system=system_prompt,
        tools=[FILE_TASK_TOOL],
        tool_choice={"type": "tool", "name": "deliver_result"},
        messages=[{"role": "user", "content": content}],
    )
    for block in resp.content:
        if block.type == "tool_use":
            return block.input
    raise RuntimeError("Model did not return the expected tool_use block")
