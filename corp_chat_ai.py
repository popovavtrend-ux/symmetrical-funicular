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
